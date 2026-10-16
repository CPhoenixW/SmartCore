from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.server.auth.security import (
    create_browser_session,
    current_session_id_from_request,
    hash_password,
    require_authenticated_actor_id,
    require_authenticated_user_id,
    revoke_all_browser_sessions,
    revoke_browser_session,
    session_user_id_from_request,
    verify_password,
)
from app.server.config import get_settings
from app.server.db.session import get_db
from app.server.new_core import crud
from app.server.new_core.models import AppUser, UserSession, nowIso

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    userId: str
    password: str


class SetupBody(BaseModel):
    password: str
    displayName: str | None = None


class RegisterBody(BaseModel):
    loginName: str
    password: str
    displayName: str | None = None


class PasswordBody(BaseModel):
    currentPassword: str
    newPassword: str


def _user_row(db: Session, user_id: str) -> dict[str, Any] | None:
    row = db.execute(
        text("SELECT userId, loginName, displayName, language, avatarUrl, passwd, role, stat FROM appUser WHERE userId = :user_id OR loginName = :user_id"),
        {"user_id": user_id},
    ).mappings().first()
    return dict(row) if row else None


def _default_user(db: Session) -> dict[str, Any]:
    crud.getCurrentUser(db)
    db.commit()
    row = _user_row(db, crud.DEFAULT_USER_ID)
    assert row is not None
    return row


def _public_user(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "userId": row["userId"],
        "loginName": row.get("loginName"),
        "role": row.get("role"),
        "displayName": row["displayName"],
        "language": row["language"],
        "avatarUrl": row["avatarUrl"],
    }


def _set_session_cookie(
    response: Response,
    request: Request,
    db: Session,
    actor_user_id: str,
    *,
    active_user_id: str | None = None,
) -> UserSession:
    settings = get_settings()
    token, row = create_browser_session(
        db,
        actor_user_id,
        active_user_id=active_user_id,
        user_agent=request.headers.get("user-agent"),
    )
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=settings.auth_session_hours * 3600,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )
    return row


def _normalized_login_name(value: str) -> str:
    login_name = value.strip()
    if len(login_name) < 3 or len(login_name) > 100:
        raise HTTPException(status_code=400, detail="login name must contain 3 to 100 characters")
    if not login_name.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(status_code=400, detail="login name may contain only letters, numbers, hyphens, and underscores")
    return login_name


@router.get("/status")
def auth_status(request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    default_user = _default_user(db)
    session_user_id = session_user_id_from_request(request)
    session_user = _user_row(db, session_user_id) if session_user_id else None
    return {
        "ok": True,
        "data": {
            "authenticated": session_user is not None,
            "needsSetup": not bool(default_user.get("passwd")),
            "registrationEnabled": get_settings().auth_registration_enabled,
            "setupEnabled": get_settings().auth_setup_enabled,
            "defaultUserId": default_user["userId"],
            "user": _public_user(session_user) if session_user else None,
        },
    }


@router.post("/setup")
def setup_password(
    body: SetupBody,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if not get_settings().auth_setup_enabled:
        raise HTTPException(status_code=403, detail="initial setup is disabled")
    user = _default_user(db)
    if user.get("passwd"):
        raise HTTPException(status_code=409, detail="initial password has already been configured")
    try:
        encoded = hash_password(body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    display_name = (body.displayName or "").strip()
    if display_name:
        db.execute(
            text("UPDATE appUser SET passwd = :passwd, displayName = :display_name WHERE userId = :user_id"),
            {"passwd": encoded, "display_name": display_name, "user_id": user["userId"]},
        )
    else:
        db.execute(
            text("UPDATE appUser SET passwd = :passwd WHERE userId = :user_id"),
            {"passwd": encoded, "user_id": user["userId"]},
        )
    db.commit()
    _set_session_cookie(response, request, db, str(user["userId"]))
    current = _user_row(db, str(user["userId"]))
    assert current is not None
    return {"ok": True, "data": _public_user(current)}


@router.post("/register")
def register(
    body: RegisterBody,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if not get_settings().auth_registration_enabled:
        raise HTTPException(status_code=403, detail="registration is disabled")
    login_name = _normalized_login_name(body.loginName)
    if db.scalar(select(AppUser).where(AppUser.loginName == login_name)) is not None:
        raise HTTPException(status_code=409, detail="login name is already in use")
    try:
        password = hash_password(body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    now = nowIso()
    user = AppUser(
        loginName=login_name,
        passwd=password,
        displayName=(body.displayName or "").strip() or login_name,
        role="user",
        stat="active",
        createdAt=now,
        updatedAt=now,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    _set_session_cookie(response, request, db, user.userId)
    return {"ok": True, "data": _public_user({
        "userId": user.userId, "loginName": user.loginName, "role": user.role,
        "displayName": user.displayName, "language": user.language, "avatarUrl": user.avatarUrl,
    })}


@router.post("/login")
def login(
    body: LoginBody,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if len(body.password) > 128 or len(body.userId) > 100:
        raise HTTPException(status_code=401, detail="invalid user ID or password")
    user_id = body.userId.strip()
    user = _user_row(db, user_id)
    if user is None or not verify_password(body.password, str(user.get("passwd") or "")):
        raise HTTPException(status_code=401, detail="invalid user ID or password")
    _set_session_cookie(response, request, db, str(user["userId"]))
    return {"ok": True, "data": _public_user(user)}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> dict[str, Any]:
    session_id = current_session_id_from_request(request)
    if session_id:
        revoke_browser_session(db, session_id)
    response.delete_cookie(get_settings().auth_cookie_name, path="/")
    return {"ok": True, "data": {"loggedOut": True}}


def _session_dict(row: UserSession, current_session_id: str | None) -> dict[str, Any]:
    return {
        "sessionId": row.sessionId,
        "actorUserId": row.actorUserId,
        "activeUserId": row.activeUserId,
        "userAgent": row.userAgent,
        "createdAt": row.createdAt,
        "lastSeenAt": row.lastSeenAt,
        "expiresAt": row.expiresAt,
        "current": row.sessionId == current_session_id,
    }


@router.get("/sessions")
def sessions(
    request: Request,
    actor_user_id: str = Depends(require_authenticated_actor_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    current_id = current_session_id_from_request(request)
    rows = db.scalars(
        select(UserSession)
        .where(
            UserSession.actorUserId == actor_user_id,
            UserSession.revokedAt.is_(None),
            UserSession.expiresAt > nowIso(),
        )
        .order_by(UserSession.lastSeenAt.desc(), UserSession.createdAt.desc())
    ).all()
    return {"ok": True, "data": [_session_dict(row, current_id) for row in rows]}


@router.delete("/sessions/{session_id}")
def revoke_session(
    session_id: str,
    request: Request,
    response: Response,
    actor_user_id: str = Depends(require_authenticated_actor_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    row = db.get(UserSession, session_id)
    if row is None or row.actorUserId != actor_user_id or row.revokedAt is not None:
        raise HTTPException(status_code=404, detail="session not found")
    current_id = current_session_id_from_request(request)
    revoke_browser_session(db, session_id)
    if current_id == session_id:
        response.delete_cookie(get_settings().auth_cookie_name, path="/")
    return {"ok": True, "data": {"sessionId": session_id, "revoked": True}}


@router.post("/logout-all")
def logout_all(
    response: Response,
    actor_user_id: str = Depends(require_authenticated_actor_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    count = revoke_all_browser_sessions(db, actor_user_id)
    response.delete_cookie(get_settings().auth_cookie_name, path="/")
    return {"ok": True, "data": {"loggedOut": True, "revokedSessions": count}}


@router.post("/password")
def change_password(
    body: PasswordBody,
    request: Request,
    response: Response,
    actor_user_id: str = Depends(require_authenticated_actor_id),
    active_user_id: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if active_user_id != actor_user_id:
        raise HTTPException(
            status_code=409,
            detail="switch to your own workspace before changing your password",
        )
    actor = db.get(AppUser, actor_user_id)
    if actor is None or not verify_password(body.currentPassword, actor.passwd):
        raise HTTPException(status_code=401, detail="current password is incorrect")
    try:
        actor.passwd = hash_password(body.newPassword)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    actor.updatedAt = nowIso()
    db.commit()
    revoked = revoke_all_browser_sessions(db, actor_user_id)
    _set_session_cookie(
        response,
        request,
        db,
        actor_user_id,
        active_user_id=active_user_id,
    )
    return {"ok": True, "data": {"passwordChanged": True, "revokedSessions": revoked}}


@router.get("/me")
def auth_me(
    user_id: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    user = _user_row(db, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="session user no longer exists")
    return {"ok": True, "data": _public_user(user)}
