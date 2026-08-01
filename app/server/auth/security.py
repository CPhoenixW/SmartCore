from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.server.config import get_settings
from app.server.db.session import SessionLocal
from app.server.new_core.models import AppUser, UserSession, nowIso

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


_SESSION_TZ = ZoneInfo("Asia/Shanghai")
_SESSION_TOUCH_INTERVAL = timedelta(minutes=5)


@dataclass(frozen=True)
class BrowserSessionContext:
    sessionId: str
    actorUserId: str
    activeUserId: str
    expiresAt: str


def session_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_browser_session(
    db: Session,
    actor_user_id: str,
    *,
    active_user_id: str | None = None,
    user_agent: str | None = None,
) -> tuple[str, UserSession]:
    actor = db.get(AppUser, actor_user_id)
    active_id = active_user_id or actor_user_id
    active = db.get(AppUser, active_id)
    if actor is None or actor.stat != "active" or active is None or active.stat != "active":
        raise ValueError("session user is unavailable")
    token = secrets.token_urlsafe(48)
    now = datetime.now(_SESSION_TZ)
    row = UserSession(
        tokenHash=session_token_hash(token),
        actorUserId=actor_user_id,
        activeUserId=active_id,
        expiresAt=(now + timedelta(hours=get_settings().auth_session_hours)).isoformat(),
        userAgent=(user_agent or "").strip()[:300] or None,
        lastSeenAt=now.isoformat(),
        createdAt=now.isoformat(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return token, row


def resolve_browser_session(
    db: Session,
    token: str | None,
    *,
    touch: bool = False,
) -> UserSession | None:
    if not token:
        return None
    row = db.scalar(select(UserSession).where(UserSession.tokenHash == session_token_hash(token)))
    if row is None or row.revokedAt is not None:
        return None
    now = datetime.now(_SESSION_TZ)
    try:
        expires_at = datetime.fromisoformat(row.expiresAt.replace("Z", "+00:00"))
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=_SESSION_TZ)
    except ValueError:
        return None
    actor = db.get(AppUser, row.actorUserId)
    active = db.get(AppUser, row.activeUserId)
    if expires_at <= now or actor is None or active is None:
        return None
    if actor.stat != "active" or active.stat != "active":
        return None
    if touch:
        last_seen = None
        if row.lastSeenAt:
            try:
                last_seen = datetime.fromisoformat(row.lastSeenAt.replace("Z", "+00:00"))
                if last_seen.tzinfo is None:
                    last_seen = last_seen.replace(tzinfo=_SESSION_TZ)
            except ValueError:
                last_seen = None
        if last_seen is None or now - last_seen >= _SESSION_TOUCH_INTERVAL:
            row.lastSeenAt = now.isoformat()
    return row


def _context(row: UserSession) -> BrowserSessionContext:
    return BrowserSessionContext(
        sessionId=row.sessionId,
        actorUserId=row.actorUserId,
        activeUserId=row.activeUserId,
        expiresAt=row.expiresAt,
    )


def browser_session_from_request(request: Request) -> BrowserSessionContext | None:
    state_key = "_smartcore_browser_session"
    checked_key = "_smartcore_browser_session_checked"
    if getattr(request.state, checked_key, False):
        return getattr(request.state, state_key, None)
    token = request.cookies.get(get_settings().auth_cookie_name)
    db = SessionLocal()
    try:
        row = resolve_browser_session(db, token, touch=True)
        context = _context(row) if row is not None else None
        if db.dirty:
            db.commit()
    finally:
        db.close()
    setattr(request.state, checked_key, True)
    setattr(request.state, state_key, context)
    return context


def create_session_token(user_id: str, *, actor_user_id: str | None = None) -> str:
    """Compatibility helper for tests and internal callers; creates a DB-backed session."""
    db = SessionLocal()
    try:
        if (actor_user_id or user_id) == "default" and db.get(AppUser, "default") is None:
            from app.server.new_core import crud

            crud.getCurrentUser(db)
            db.commit()
        token, _ = create_browser_session(
            db,
            actor_user_id or user_id,
            active_user_id=user_id,
        )
        return token
    finally:
        db.close()


def _decode_context(token: str | None) -> BrowserSessionContext | None:
    db = SessionLocal()
    try:
        row = resolve_browser_session(db, token)
        return _context(row) if row is not None else None
    finally:
        db.close()


def decode_session_token(token: str | None) -> str | None:
    context = _decode_context(token)
    return context.activeUserId if context else None


def decode_session_actor_id(token: str | None) -> str | None:
    context = _decode_context(token)
    return context.actorUserId if context else None


def session_user_id_from_request(request: Request) -> str | None:
    context = browser_session_from_request(request)
    return context.activeUserId if context else None


def require_authenticated_user_id(request: Request) -> str:
    user_id = session_user_id_from_request(request)
    if user_id is None:
        raise HTTPException(status_code=401, detail="authentication required")
    return user_id


def require_authenticated_actor_id(request: Request) -> str:
    context = browser_session_from_request(request)
    if context is None:
        raise HTTPException(status_code=401, detail="authentication required")
    return context.actorUserId


def current_session_id_from_request(request: Request) -> str | None:
    context = browser_session_from_request(request)
    return context.sessionId if context else None


def revoke_browser_session(db: Session, session_id: str) -> bool:
    row = db.get(UserSession, session_id)
    if row is None or row.revokedAt is not None:
        return False
    row.revokedAt = nowIso()
    db.commit()
    return True


def revoke_all_browser_sessions(db: Session, actor_user_id: str) -> int:
    rows = list(
        db.scalars(
            select(UserSession).where(
                UserSession.actorUserId == actor_user_id,
                UserSession.revokedAt.is_(None),
            )
        )
    )
    now = nowIso()
    for row in rows:
        row.revokedAt = now
    db.commit()
    return len(rows)


def switch_active_browser_user(request: Request, db: Session, active_user_id: str) -> UserSession:
    context = browser_session_from_request(request)
    if context is None:
        raise HTTPException(status_code=401, detail="authentication required")
    row = db.get(UserSession, context.sessionId)
    if row is None or row.revokedAt is not None:
        raise HTTPException(status_code=401, detail="authentication required")
    row.activeUserId = active_user_id
    row.lastSeenAt = nowIso()
    db.commit()
    setattr(request.state, "_smartcore_browser_session", _context(row))
    return row
