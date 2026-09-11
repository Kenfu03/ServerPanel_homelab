import importlib
import os
from collections.abc import AsyncIterator
from unittest.mock import patch

import httpx2
import pytest
from argon2 import PasswordHasher


os.environ["ADMIN_USERNAME"] = "kenek"
os.environ["ADMIN_PASSWORD_HASH"] = PasswordHasher().hash("correct-test-password")
os.environ["SESSION_SECRET"] = "test-only-session-secret-that-is-long-enough-for-validation"
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


@pytest.mark.anyio
async def test_normal_identity_creates_session_and_me_returns_user(
    client: httpx2.AsyncClient,
) -> None:
    response = await client.post("/api/auth/identify", json={"name": "  Angie  "})

    assert response.status_code == 200
    assert response.json() == {
        "requires_password": False,
        "user": {"name": "Angie", "is_admin": False},
    }
    assert "HttpOnly" in response.headers["set-cookie"]
    assert (await client.get("/api/auth/me")).json() == {
        "authenticated": True,
        "name": "Angie",
        "is_admin": False,
    }


@pytest.mark.parametrize("name", ["", "   ", "a" * 41])
@pytest.mark.anyio
async def test_invalid_normal_identity_is_rejected(
    client: httpx2.AsyncClient,
    name: str,
) -> None:
    response = await client.post("/api/auth/identify", json={"name": name})

    assert response.status_code == 422


@pytest.mark.parametrize("name", ["kenek", "Kenek", "KENEK", " KeNeK ", "Ｋｅｎｅｋ"])
@pytest.mark.anyio
async def test_reserved_admin_identity_always_requires_password(
    client: httpx2.AsyncClient,
    name: str,
) -> None:
    response = await client.post("/api/auth/identify", json={"name": name})

    assert response.status_code == 200
    assert response.json() == {"requires_password": True, "user": None}
    assert (await client.get("/api/auth/me")).json()["authenticated"] is False


@pytest.mark.anyio
async def test_admin_login_and_me(client: httpx2.AsyncClient) -> None:
    response = await client.post(
        "/api/auth/login",
        json={"name": "KENEK", "password": "correct-test-password"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "authenticated": True,
        "name": "Kenek",
        "is_admin": True,
    }
    assert (await client.get("/api/auth/me")).json()["is_admin"] is True


@pytest.mark.anyio
async def test_wrong_admin_password_is_rejected(client: httpx2.AsyncClient) -> None:
    response = await client.post(
        "/api/auth/login",
        json={"name": "Kenek", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid credentials"}
    assert (await client.get("/api/auth/me")).json()["authenticated"] is False


@pytest.mark.anyio
async def test_logout_clears_session(client: httpx2.AsyncClient) -> None:
    await client.post("/api/auth/identify", json={"name": "Mapache"})

    response = await client.post("/api/auth/logout")

    assert response.status_code == 200
    assert response.json() == {"success": True}
    assert (await client.get("/api/auth/me")).json()["authenticated"] is False


@pytest.mark.parametrize("endpoint", ["start", "stop", "restart"])
@pytest.mark.anyio
async def test_anonymous_server_controls_are_rejected(
    client: httpx2.AsyncClient,
    endpoint: str,
) -> None:
    response = await client.post(f"/api/{endpoint}")

    assert response.status_code == 401


@pytest.mark.parametrize("identity", ["normal", "admin"])
@pytest.mark.parametrize("endpoint", ["start", "stop", "restart"])
@pytest.mark.anyio
async def test_identified_users_can_use_server_controls(
    client: httpx2.AsyncClient,
    identity: str,
    endpoint: str,
) -> None:
    if identity == "admin":
        await client.post(
            "/api/auth/login",
            json={"name": "Kenek", "password": "correct-test-password"},
        )
    else:
        await client.post("/api/auth/identify", json={"name": "Angie"})

    with patch.object(main_module, "minecraft_command", return_value=True) as command:
        response = await client.post(f"/api/{endpoint}")

    assert response.status_code == 200
    assert response.json() == {"success": True}
    command.assert_called_once_with(endpoint)
