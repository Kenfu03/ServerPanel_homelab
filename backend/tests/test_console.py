import importlib
import os
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import patch

import httpx2
import pytest
from argon2 import PasswordHasher


os.environ["ADMIN_USERNAME"] = "kenek"
os.environ["ADMIN_PASSWORD_HASH"] = PasswordHasher().hash("correct-test-password")
os.environ["SESSION_SECRET"] = "console-test-session-secret-that-is-long-enough-to-use"
os.environ["SESSION_COOKIE_SECURE"] = "false"
os.environ["SESSION_COOKIE_SAMESITE"] = "lax"

main_module = importlib.import_module("app.main")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client() -> AsyncIterator[httpx2.AsyncClient]:
    transport = httpx2.ASGITransport(app=main_module.app)
    async with httpx2.AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client


async def login_admin(client: httpx2.AsyncClient) -> None:
    response = await client.post(
        "/api/auth/login",
        json={"name": "Kenek", "password": "correct-test-password"},
    )
    assert response.status_code == 200


@pytest.mark.parametrize(
    ("method", "endpoint", "json"),
    [
        ("GET", "/api/console/logs", None),
        ("POST", "/api/console/command", {"command": "list"}),
    ],
)
@pytest.mark.anyio
async def test_anonymous_console_access_is_rejected(
    client: httpx2.AsyncClient,
    method: str,
    endpoint: str,
    json: dict[str, str] | None,
) -> None:
    response = await client.request(method, endpoint, json=json)

    assert response.status_code == 401


@pytest.mark.parametrize(
    ("method", "endpoint", "json"),
    [
        ("GET", "/api/console/logs", None),
        ("POST", "/api/console/command", {"command": "list"}),
    ],
)
@pytest.mark.anyio
async def test_normal_user_console_access_is_rejected(
    client: httpx2.AsyncClient,
    method: str,
    endpoint: str,
    json: dict[str, str] | None,
) -> None:
    await client.post("/api/auth/identify", json={"name": "Angie"})

    response = await client.request(method, endpoint, json=json)

    assert response.status_code == 403


@pytest.mark.anyio
async def test_admin_can_read_recent_log_lines(
    client: httpx2.AsyncClient,
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "latest.log"
    log_path.write_text("".join(f"line-{index:03d}\n" for index in range(350)))
    await login_admin(client)

    with patch.object(main_module, "MINECRAFT_LOG_PATH", log_path):
        response = await client.get("/api/console/logs")

    assert response.status_code == 200
    assert response.json() == {
        "lines": [f"line-{index:03d}" for index in range(150, 350)],
        "available": True,
        "message": None,
    }


@pytest.mark.anyio
async def test_console_filters_rcon_bookkeeping_and_preserves_useful_logs(
    client: httpx2.AsyncClient,
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "latest.log"
    useful_lines = [
        "[12:00:00] [Server thread/INFO]: <Alex> hello everyone",
        "[12:00:01] [Server thread/INFO]: Alex joined the game",
        "[12:00:02] [Server thread/INFO]: Alex left the game",
        "[12:00:03] [Server thread/WARN]: Can't keep up!",
        "[12:00:04] [Server thread/ERROR]: Example mod error",
        "[12:00:05] [Server thread/INFO]: Saving the game (this may take a moment!)",
        "[12:00:06] [Server thread/INFO]: RCON command returned 3 players",
    ]
    noise_lines = [
        "[12:00:07] [RCON Listener #1/INFO]: Thread RCON Client /127.0.0.1 started",
        "[12:00:08] [RCON Client /127.0.0.1 #240/INFO]: Thread RCON Client /127.0.0.1 shutting down",
        "[12:00:09] [minecraft/RconClient/INFO]: Thread RCON Client /127.0.0.1 started",
    ]
    log_path.write_text("\n".join(useful_lines + noise_lines) + "\n")
    await login_admin(client)

    with patch.object(main_module, "MINECRAFT_LOG_PATH", log_path):
        response = await client.get("/api/console/logs")

    assert response.status_code == 200
    assert response.json()["lines"] == useful_lines


@pytest.mark.anyio
async def test_console_reads_past_rcon_noise_for_latest_useful_lines(
    client: httpx2.AsyncClient,
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "latest.log"
    useful_lines = [
        f"[12:00:{index % 60:02d}] [Server thread/INFO]: useful-{index:03d}"
        for index in range(250)
    ]
    noise_lines = [
        f"[12:01:{index % 60:02d}] [RCON Client /127.0.0.1 #{index}/INFO]: "
        "Thread RCON Client /127.0.0.1 shutting down"
        for index in range(600)
    ]
    log_path.write_text("\n".join(useful_lines + noise_lines) + "\n")
    await login_admin(client)

    with patch.object(main_module, "MINECRAFT_LOG_PATH", log_path):
        response = await client.get("/api/console/logs")

    assert response.status_code == 200
    assert response.json()["lines"] == useful_lines[-200:]


@pytest.mark.anyio
async def test_missing_log_file_is_handled(
    client: httpx2.AsyncClient,
    tmp_path: Path,
) -> None:
    await login_admin(client)

    with patch.object(main_module, "MINECRAFT_LOG_PATH", tmp_path / "missing.log"):
        response = await client.get("/api/console/logs")

    assert response.status_code == 200
    assert response.json()["lines"] == []
    assert response.json()["available"] is False


@pytest.mark.anyio
async def test_admin_command_uses_rcon(client: httpx2.AsyncClient) -> None:
    await login_admin(client)

    with patch.object(main_module, "execute_rcon_command", return_value="Listed players") as rcon:
        response = await client.post(
            "/api/console/command",
            json={"command": "  list  "},
        )

    assert response.status_code == 200
    assert response.json() == {"success": True, "response": "Listed players"}
    rcon.assert_called_once_with("list")


@pytest.mark.parametrize("command", ["", "   ", "x" * 1025])
@pytest.mark.anyio
async def test_invalid_commands_are_rejected(
    client: httpx2.AsyncClient,
    command: str,
) -> None:
    await login_admin(client)

    with patch.object(main_module, "execute_rcon_command") as rcon:
        response = await client.post(
            "/api/console/command",
            json={"command": command},
        )

    assert response.status_code == 422
    rcon.assert_not_called()


@pytest.mark.anyio
async def test_rcon_failure_is_reported_cleanly(client: httpx2.AsyncClient) -> None:
    await login_admin(client)

    with patch.object(main_module, "execute_rcon_command", side_effect=ConnectionError("secret")):
        response = await client.post(
            "/api/console/command",
            json={"command": "list"},
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "Minecraft RCON is unavailable"}
