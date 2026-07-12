from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import text
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

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    userId: str
    password: str


class SetupBody(BaseModel):
    password: str
    displayName: str | None = None


def _user_row(db: Session, user_id: str) -> dict[str, Any] | None:
    row = db.execute(
        text("SELECT userId, displayName, language, avatarUrl, passwd FROM appUser WHERE userId = :user_id"),
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
    _set_session_cookie(response, user_id)
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
