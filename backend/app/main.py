import os
import re
import subprocess
import time
import psutil

from fastapi import Depends, Response, status as http_status
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from mctools import RCONClient

from .auth import (
    AdminLoginRequest,
    IdentityRequest,
    RESERVED_ADMIN_USERNAME,
    SessionUser,
    clear_session_cookie,
    get_session_user,
    is_reserved_admin_name,
    normalize_name,
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


@app.get("/", response_class=HTMLResponse)
def home():
    return """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Minecraft Homelab</title>

    <style>
        body {
            font-family: Arial, sans-serif;
            background: #151515;
            color: white;
            text-align: center;
            margin-top: 100px;
        }

        .panel {
            width: 400px;
            margin: auto;
            background: #222;
            padding: 30px;
            border-radius: 15px;
        }

        button {
            padding: 12px 20px;
            margin: 5px;
            font-size: 16px;
            cursor: pointer;
        }

        button:disabled {
            cursor: not-allowed;
            opacity: 0.5;
        }

        #status {
            font-size: 24px;
            margin: 25px;
        }

        #message {
            min-height: 20px;
            margin-top: 15px;
        }

        #players {
            font-size: 18px;
            margin-bottom: 15px;
        }

        #playerList {
            background: #181818;
            padding: 12px;
            margin: 15px 0 25px 0;
            border-radius: 8px;
        }

        .player {
            padding: 4px;
        }

        .stats {
            display: flex;
            justify-content: space-between;
            gap: 10px;
            margin: 20px 0;
        }

        .stat {
            flex: 1;
            background: #181818;
            padding: 15px 5px;
            border-radius: 8px;
        }

        .stat-title {
            font-size: 11px;
            color: #888;
            margin-bottom: 7px;
        }

        .stat-value {
            font-size: 18px;
            font-weight: bold;
        }
    </style>
</head>

<body>

<div class="panel">

    <h1>Minecraft Server</h1>

    <div id="status">Checking...</div>

    <div id="players">
        Players: -- / --
    </div>

    <div id="playerList">
        <p>No players online</p>
    </div>

    <div class="stats">

        <div class="stat">
            <div class="stat-title">UPTIME</div>
            <div id="uptime" class="stat-value">--</div>
        </div>

        <div class="stat">
            <div class="stat-title">RAM</div>
            <div id="memory" class="stat-value">--</div>
        </div>

        <div class="stat">
            <div class="stat-title">CPU</div>
            <div id="cpu" class="stat-value">--</div>
        </div>

    </div>

    <button id="startButton" onclick="sendCommand('start')">
        Start
    </button>

    <button id="stopButton" onclick="sendCommand('stop')">
        Stop
    </button>

    <button id="restartButton" onclick="sendCommand('restart')">
        Restart
    </button>

    <div id="message"></div>

</div>

<script>
    function formatUptime(seconds) {
        const days = Math.floor(seconds / 86400);
        seconds %= 86400;

        const hours = Math.floor(seconds / 3600);
        seconds %= 3600;

        const minutes = Math.floor(seconds / 60);

        if (days > 0) {
            return `${days}d ${hours}h`;
        }

        if (hours > 0) {
            return `${hours}h ${minutes}m`;
        }

        return `${minutes}m`;
    }

    async function updateStatus() {
        try {
            const response = await fetch('/api/status', {
                cache: 'no-store'
            });

            const data = await response.json();

            const statusElement = document.getElementById('status');
            const playersElement = document.getElementById('players');
            const playerListElement = document.getElementById('playerList');
            const uptimeElement = document.getElementById('uptime');
            const memoryElement = document.getElementById('memory');
            const cpuElement = document.getElementById('cpu');

            if (data.online) {
                statusElement.textContent = '🟢 ONLINE';

                playersElement.textContent =
                    `Players: ${data.players} / ${data.max_players}`;

                if (data.player_names.length > 0) {
                    playerListElement.innerHTML = '';

                    for (const player of data.player_names) {
                        const element = document.createElement('div');
                        element.className = 'player';
                        element.textContent = '• ' + player;

                        playerListElement.appendChild(element);
                    }
                } else {
                    playerListElement.innerHTML =
                        '<p>No players online</p>';
                }

                uptimeElement.textContent = formatUptime(data.uptime);

                memoryElement.textContent =
                    `${(data.memory_mb / 1024).toFixed(1)} GB`;

                cpuElement.textContent =
                    `${data.cpu_percent.toFixed(1)}%`;

            } else {
                statusElement.textContent = '🔴 OFFLINE';
                playersElement.textContent = 'Players: -- / --';
                playerListElement.innerHTML =
                    '<p>Server offline</p>';
                uptimeElement.textContent = '--';
                memoryElement.textContent = '--';
                cpuElement.textContent = '--';
            }

        } catch (error) {
            console.error('Status error:', error);

            document.getElementById('status').textContent =
                '⚠️ ERROR';
        }
    }


    async function sendCommand(action) {
        console.log('Sending:', action);

        const message = document.getElementById('message');

        message.textContent = 'Sending command...';

        try {
            const response = await fetch('/api/' + action, {
                method: 'POST'
            });

            const data = await response.json();

            console.log('Response:', data);

            if (data.success) {
                message.textContent = action + ' command sent successfully.';
            } else {
                message.textContent = 'Command failed.';
            }

            setTimeout(updateStatus, 1000);

        } catch (error) {
            console.error('Command error:', error);
            message.textContent = 'Request failed.';
        }
    }


    updateStatus();

    setInterval(updateStatus, 5000);
</script>

</body>
</html>
"""
