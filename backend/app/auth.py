import hashlib
import os
import unicodedata
from dataclasses import dataclass
from typing import Literal, cast

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import HTTPException, Request, Response, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel, field_validator


RESERVED_ADMIN_USERNAME = "kenek"
DEFAULT_SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 7
MAX_DISPLAY_NAME_LENGTH = 40
SESSION_COOKIE_NAME = "mcpanel_session"
SESSION_SIGNING_SALT = "mcpanel-identity-v1"


class IdentityRequest(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return clean_display_name(value)


class AdminLoginRequest(IdentityRequest):
    password: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not value or len(value) > 1024:
            raise ValueError("Password is required")
        return value


@dataclass(frozen=True)
class SessionUser:
    display_name: str
    normalized_name: str
    is_admin: bool


def clean_display_name(value: str) -> str:
    display_name = " ".join(unicodedata.normalize("NFKC", value).strip().split())

    if not display_name:
        raise ValueError("Name is required")
    if len(display_name) > MAX_DISPLAY_NAME_LENGTH:
        raise ValueError(f"Name must be at most {MAX_DISPLAY_NAME_LENGTH} characters")
    if any(not character.isprintable() for character in display_name):
        raise ValueError("Name contains unsupported characters")

    return display_name


def normalize_name(display_name: str) -> str:
    return display_name.casefold()


def is_reserved_admin_name(display_name: str) -> bool:
    return normalize_name(display_name) == RESERVED_ADMIN_USERNAME


def _get_boolean_setting(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().casefold() in {"1", "true", "yes", "on"}


def _get_cookie_samesite() -> Literal["lax", "strict", "none"]:
    value = os.getenv("SESSION_COOKIE_SAMESITE", "lax").strip().casefold()
    if value not in {"lax", "strict", "none"}:
        raise RuntimeError("SESSION_COOKIE_SAMESITE must be lax, strict, or none")
    return cast(Literal["lax", "strict", "none"], value)


def _get_session_max_age() -> int:
    try:
        max_age = int(os.getenv("SESSION_MAX_AGE_SECONDS", str(DEFAULT_SESSION_MAX_AGE_SECONDS)))
    except ValueError as error:
        raise RuntimeError("SESSION_MAX_AGE_SECONDS must be an integer") from error

    if max_age <= 0:
        raise RuntimeError("SESSION_MAX_AGE_SECONDS must be greater than zero")
    return max_age


def _get_session_serializer() -> URLSafeTimedSerializer:
    secret = os.getenv("SESSION_SECRET", "")
    if len(secret) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured",
        )

    return URLSafeTimedSerializer(
        secret_key=secret,
        salt=SESSION_SIGNING_SALT,
        signer_kwargs={"digest_method": hashlib.sha256},
    )


def _session_payload(user: SessionUser) -> dict[str, str | bool]:
    return {
        "display_name": user.display_name,
        "normalized_name": user.normalized_name,
        "is_admin": user.is_admin,
    }


def set_session_cookie(response: Response, user: SessionUser) -> None:
    token = _get_session_serializer().dumps(_session_payload(user))
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=_get_session_max_age(),
        httponly=True,
        secure=_get_boolean_setting("SESSION_COOKIE_SECURE", False),
        samesite=_get_cookie_samesite(),
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        httponly=True,
        secure=_get_boolean_setting("SESSION_COOKIE_SECURE", False),
        samesite=_get_cookie_samesite(),
        path="/",
    )


def get_session_user(request: Request) -> SessionUser | None:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None

    try:
        payload = _get_session_serializer().loads(token, max_age=_get_session_max_age())
    except (BadSignature, SignatureExpired, HTTPException):
        return None

    if not isinstance(payload, dict):
        return None

    display_name = payload.get("display_name")
    normalized_name = payload.get("normalized_name")
    is_admin = payload.get("is_admin")
    if not isinstance(display_name, str) or not isinstance(normalized_name, str):
        return None
    if type(is_admin) is not bool:
        return None

    try:
        cleaned_name = clean_display_name(display_name)
    except ValueError:
        return None

    expected_normalized_name = normalize_name(cleaned_name)
    if normalized_name != expected_normalized_name:
        return None

    reserved_name = expected_normalized_name == RESERVED_ADMIN_USERNAME
    if reserved_name != is_admin:
        return None

    return SessionUser(cleaned_name, expected_normalized_name, is_admin)


def require_user(request: Request) -> SessionUser:
    user = get_session_user(request)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user


def require_admin(request: Request) -> SessionUser:
    user = require_user(request)
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required",
        )
    return user


def verify_admin_password(password: str) -> bool:
    configured_username = os.getenv("ADMIN_USERNAME", RESERVED_ADMIN_USERNAME).strip().casefold()
    password_hash = os.getenv("ADMIN_PASSWORD_HASH", "")

    if configured_username != RESERVED_ADMIN_USERNAME:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured",
        )
    if not password_hash:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured",
        )

    try:
        return PasswordHasher().verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False
