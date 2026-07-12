from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request

from app.config import get_settings

_SESSION_VERSION = 1
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


@lru_cache(maxsize=1)
def auth_secret() -> bytes:
    settings = get_settings()
    if settings.auth_secret:
        return settings.auth_secret.encode("utf-8")

    path = Path(settings.auth_secret_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing.encode("utf-8")

    generated = secrets.token_urlsafe(48)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(generated, encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(path)
    return generated.encode("utf-8")


def validate_password(password: str) -> None:
    if len(password) < 8:
        raise ValueError("password must contain at least 8 characters")
    if len(password) > 128:
        raise ValueError("password must not exceed 128 characters")


def hash_password(password: str) -> str:
    validate_password(password)
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64encode(salt)}${_b64encode(digest)}"


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        algorithm, n, r, p, salt_value, expected_value = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_b64decode(salt_value),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(_b64decode(expected_value)),
        )
        return hmac.compare_digest(actual, _b64decode(expected_value))
    except (ValueError, TypeError):
        return False


def create_session_token(user_id: str) -> str:
    settings = get_settings()
    payload: dict[str, Any] = {
        "v": _SESSION_VERSION,
        "u": user_id,
        "exp": int(time.time()) + settings.auth_session_hours * 3600,
    }
    encoded = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _b64encode(hmac.new(auth_secret(), encoded.encode("ascii"), hashlib.sha256).digest())
    return f"{encoded}.{signature}"


def decode_session_token(token: str | None) -> str | None:
    if not token:
        return None
    try:
        encoded, signature = token.split(".", 1)
        expected = _b64encode(hmac.new(auth_secret(), encoded.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            return None
        payload = json.loads(_b64decode(encoded))
        if payload.get("v") != _SESSION_VERSION or int(payload.get("exp", 0)) < int(time.time()):
            return None
        user_id = str(payload.get("u") or "").strip()
        return user_id or None
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def session_user_id_from_request(request: Request) -> str | None:
    return decode_session_token(request.cookies.get(get_settings().auth_cookie_name))


def require_authenticated_user_id(request: Request) -> str:
    user_id = session_user_id_from_request(request)
    if user_id is None:
        raise HTTPException(status_code=401, detail="authentication required")
    return user_id
