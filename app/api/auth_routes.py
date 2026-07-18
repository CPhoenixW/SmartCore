from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.auth.security import (
    create_session_token,
    hash_password,
    require_authenticated_user_id,
    session_user_id_from_request,
    verify_password,
)
from app.config import get_settings
from app.db.session import get_db
from app.new_core import crud
from app.new_core.models import AppUser, nowIso

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


def _set_session_cookie(response: Response, user_id: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=create_session_token(user_id),
        max_age=settings.auth_session_hours * 3600,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )


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
            "defaultUserId": default_user["userId"],
            "user": _public_user(session_user) if session_user else None,
        },
    }


@router.post("/setup")
def setup_password(
    body: SetupBody,
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
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
    _set_session_cookie(response, str(user["userId"]))
    current = _user_row(db, str(user["userId"]))
    assert current is not None
    return {"ok": True, "data": _public_user(current)}


@router.post("/register")
def register(
    body: RegisterBody,
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
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
    _set_session_cookie(response, user.userId)
    return {"ok": True, "data": _public_user({
        "userId": user.userId, "loginName": user.loginName, "role": user.role,
        "displayName": user.displayName, "language": user.language, "avatarUrl": user.avatarUrl,
    })}


@router.post("/login")
def login(
    body: LoginBody,
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    user_id = body.userId.strip()
    user = _user_row(db, user_id)
    if user is None or not verify_password(body.password, str(user.get("passwd") or "")):
        raise HTTPException(status_code=401, detail="invalid user ID or password")
    _set_session_cookie(response, str(user["userId"]))
    return {"ok": True, "data": _public_user(user)}


@router.post("/logout")
def logout(response: Response) -> dict[str, Any]:
    response.delete_cookie(get_settings().auth_cookie_name, path="/")
    return {"ok": True, "data": {"loggedOut": True}}


@router.get("/me")
def auth_me(
    user_id: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    user = _user_row(db, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="session user no longer exists")
    return {"ok": True, "data": _public_user(user)}
