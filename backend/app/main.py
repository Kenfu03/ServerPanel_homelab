import os
import re
import subprocess
import time
from pathlib import Path

import psutil

from fastapi import Depends, HTTPException, Response, status as http_status
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from mctools import RCONClient
from pydantic import BaseModel, field_validator

from .auth import (
    AdminLoginRequest,
    IdentityRequest,
    RESERVED_ADMIN_USERNAME,
    SessionUser,
    clear_session_cookie,
    get_session_user,
    is_reserved_admin_name,
    normalize_name,
    require_admin,
    require_user,
    set_session_cookie,
    verify_admin_password,
)


load_dotenv("/opt/mcpanel/backend/.env")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4321",
        "http://127.0.0.1:4321",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

RCON_HOST = os.getenv("RCON_HOST", "127.0.0.1")
RCON_PORT = int(os.getenv("RCON_PORT", "25575"))
RCON_PASSWORD = os.getenv("RCON_PASSWORD")
MINECRAFT_LOG_PATH = Path(
    os.getenv("MINECRAFT_LOG_PATH", "/opt/minecraft/server/logs/latest.log")
)
CONSOLE_LOG_LINE_COUNT = 200
CONSOLE_LOG_MAX_BYTES = 1024 * 1024
MAX_CONSOLE_COMMAND_LENGTH = 1024

RCON_CONNECTION_SOURCE_PATTERN = re.compile(
    r"\[(?:(?:[^\]/\s]+/)?RconClient|RCON Listener|RCON Client)\b[^\]]*\]",
    re.IGNORECASE,
)
RCON_CLIENT_LIFECYCLE_PATTERN = re.compile(
    r"\bThread RCON Client\b.*\b(?:started|shutting down)\b",
    re.IGNORECASE,
)


class ConsoleCommandRequest(BaseModel):
    command: str

    @field_validator("command")
    @classmethod
    def validate_command(cls, value: str) -> str:
        command = value.strip()
        if not command:
            raise ValueError("Command is required")
        if len(command) > MAX_CONSOLE_COMMAND_LENGTH:
            raise ValueError(
                f"Command must be at most {MAX_CONSOLE_COMMAND_LENGTH} characters"
            )
        if "\n" in command or "\r" in command:
            raise ValueError("Command must be a single line")
        return command


def is_internal_rcon_connection_line(line: str) -> bool:
    """Identify Minecraft's repetitive RCON connection lifecycle bookkeeping."""
    return bool(
        RCON_CONNECTION_SOURCE_PATTERN.search(line)
        or RCON_CLIENT_LIFECYCLE_PATTERN.search(line)
    )


def tail_log_file(path: Path, line_count: int = CONSOLE_LOG_LINE_COUNT) -> list[str]:
    """Read the last useful log lines without loading the entire file."""
    if line_count <= 0:
        return []

    chunk_size = 8192
    pending_line = b""
    useful_lines_reversed: list[str] = []

    with path.open("rb") as log_file:
        log_file.seek(0, os.SEEK_END)
        position = log_file.tell()
        bytes_read = 0
        reading_file_end = True

        while (
            position > 0
            and len(useful_lines_reversed) < line_count
            and bytes_read < CONSOLE_LOG_MAX_BYTES
        ):
            read_size = min(chunk_size, position, CONSOLE_LOG_MAX_BYTES - bytes_read)
            position -= read_size
            bytes_read += read_size
            log_file.seek(position)
            parts = (log_file.read(read_size) + pending_line).split(b"\n")
            pending_line = parts[0]
            complete_lines = parts[1:]

            # A final newline produces an empty split item, not an empty log line.
            if reading_file_end and complete_lines and complete_lines[-1] == b"":
                complete_lines.pop()
            reading_file_end = False

            for raw_line in reversed(complete_lines):
                line = raw_line.rstrip(b"\r").decode("utf-8", errors="replace")
                if not is_internal_rcon_connection_line(line):
                    useful_lines_reversed.append(line)
                    if len(useful_lines_reversed) == line_count:
                        break

        if position == 0 and len(useful_lines_reversed) < line_count:
            first_line = pending_line.rstrip(b"\r").decode("utf-8", errors="replace")
            if first_line and not is_internal_rcon_connection_line(first_line):
                useful_lines_reversed.append(first_line)

    return list(reversed(useful_lines_reversed))


def execute_rcon_command(command: str) -> str:
    if not RCON_PASSWORD:
        raise RuntimeError("RCON is not configured")

    client = RCONClient(RCON_HOST, port=RCON_PORT)
    try:
        if not client.login(RCON_PASSWORD):
            raise RuntimeError("RCON authentication failed")
        response = client.command(command)
        return "" if response is None else str(response)
    finally:
        try:
            client.stop()
        except Exception:
            pass

def get_minecraft_process():
    for process in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if process.info["name"] != "java":
                continue

            cmdline = process.info["cmdline"]

            if not cmdline:
                continue

            command = " ".join(cmdline)

            if "neoforge" in command.lower():
                return process

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return None

def minecraft_metrics():
    process = get_minecraft_process()

    if process is None:
        return {
            "uptime": 0,
            "memory_mb": 0,
            "cpu_percent": 0,
        }

    try:
        uptime = int(time.time() - process.create_time())

        memory = process.memory_info().rss
        memory_mb = round(memory / 1024 / 1024, 1)

        cpu = process.cpu_percent(interval=0.1)

        return {
            "uptime": uptime,
            "memory_mb": memory_mb,
            "cpu_percent": round(cpu, 1),
        }

    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return {
            "uptime": 0,
            "memory_mb": 0,
            "cpu_percent": 0,
        }

def minecraft_command(action: str):
    allowed_actions = {"start", "stop", "restart"}

    if action not in allowed_actions:
        return False

    result = subprocess.run(
        ["sudo", "-n", "/usr/bin/systemctl", action, "minecraft"],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"Command failed: {result.stderr}")

    return result.returncode == 0


def minecraft_status():
    client = RCONClient(RCON_HOST, port=RCON_PORT)

    try:
        if not client.login(RCON_PASSWORD):
            return {
                "online": False,
                "players": 0,
                "max_players": 0,
                "player_names": [],
            }

        response = client.command("list")

        # Remove Minecraft/terminal ANSI formatting codes
        response = re.sub(r"\x1b\[[0-9;]*m", "", response)

        # Example:
        # There are 2 of a max of 20 players online: Kenek, Friend
        before_names, _, names = response.partition(":")

        parts = before_names.split()

        current_players = int(parts[2])
        max_players = int(parts[7])

        player_names = [
            name.strip()
            for name in names.split(",")
            if name.strip()
        ]

        return {
            "online": True,
            "players": current_players,
            "max_players": max_players,
            "player_names": player_names,
        }

    except Exception as error:
        print(f"RCON status failed: {error}")

        return {
            "online": False,
            "players": 0,
            "max_players": 0,
            "player_names": [],
        }

    finally:
        try:
            client.stop()
        except Exception:
            pass


@app.get("/api/status")
def status():
    server = minecraft_status()
    metrics = minecraft_metrics()

    return {
        **server,
        **metrics,
    }


@app.post("/api/auth/identify")
def identify(payload: IdentityRequest, response: Response):
    if is_reserved_admin_name(payload.name):
        clear_session_cookie(response)
        return {"requires_password": True, "user": None}

    user = SessionUser(
        display_name=payload.name,
        normalized_name=normalize_name(payload.name),
        is_admin=False,
    )
    set_session_cookie(response, user)
    return {
        "requires_password": False,
        "user": {"name": user.display_name, "is_admin": user.is_admin},
    }


@app.post("/api/auth/login")
def login(payload: AdminLoginRequest, response: Response):
    if not is_reserved_admin_name(payload.name) or not verify_admin_password(payload.password):
        error_response = JSONResponse(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Invalid credentials"},
        )
        clear_session_cookie(error_response)
        return error_response

    user = SessionUser(
        display_name="Kenek",
        normalized_name=RESERVED_ADMIN_USERNAME,
        is_admin=True,
    )
    set_session_cookie(response, user)
    return {"authenticated": True, "name": user.display_name, "is_admin": True}


@app.get("/api/auth/me")
def current_user(request_user: SessionUser | None = Depends(get_session_user)):
    if request_user is None:
        return {"authenticated": False, "name": None, "is_admin": False}
    return {
        "authenticated": True,
        "name": request_user.display_name,
        "is_admin": request_user.is_admin,
    }


@app.post("/api/auth/logout")
def logout(response: Response):
    clear_session_cookie(response)
    return {"success": True}

@app.post("/api/start")
def start(_user: SessionUser = Depends(require_user)):
    return {"success": minecraft_command("start")}


@app.post("/api/stop")
def stop(_user: SessionUser = Depends(require_user)):
    return {"success": minecraft_command("stop")}


@app.post("/api/restart")
def restart(_user: SessionUser = Depends(require_user)):
    return {"success": minecraft_command("restart")}


@app.get("/api/console/logs")
def console_logs(_admin: SessionUser = Depends(require_admin)):
    try:
        lines = tail_log_file(MINECRAFT_LOG_PATH)
    except FileNotFoundError:
        return {
            "lines": [],
            "available": False,
            "message": "Minecraft latest.log is not available yet.",
        }
    except OSError as error:
        print(f"Minecraft log read failed: {error}")
        return {
            "lines": [],
            "available": False,
            "message": "Minecraft latest.log cannot be read.",
        }

    return {"lines": lines, "available": True, "message": None}


@app.post("/api/console/command")
def console_command(
    payload: ConsoleCommandRequest,
    _admin: SessionUser = Depends(require_admin),
):
    try:
        response = execute_rcon_command(payload.command)
    except Exception as error:
        print(f"RCON console command failed: {error}")
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Minecraft RCON is unavailable",
        ) from error

    return {"success": True, "response": response}
