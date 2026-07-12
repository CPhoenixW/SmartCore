from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import create_session_token, require_authenticated_actor_id
from app.config import get_settings
from app.db.session import get_db
from app.new_core.models import ActLog, AppUser, nowIso

router = APIRouter(prefix="/api/admin", tags=["admin"])


class ActiveUserBody(BaseModel):
    userId: str


def _public(user: AppUser) -> dict[str, Any]:
    return {"userId": user.userId, "loginName": user.loginName, "displayName": user.displayName, "role": user.role, "stat": user.stat}


def _actor(db: Session, userId: str) -> AppUser:
    user = db.get(AppUser, userId)
    if user is None or user.stat != "active":
        raise HTTPException(status_code=401, detail="session user is unavailable")
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="administrator role required")
    return user


@router.get("/users")
def users(userId: str = Depends(require_authenticated_actor_id), db: Session = Depends(get_db)) -> dict[str, Any]:
    _actor(db, userId)
    return {"ok": True, "data": [_public(row) for row in db.scalars(select(AppUser).where(AppUser.stat == "active").order_by(AppUser.createdAt))]}


@router.post("/activeUser")
def activeUser(body: ActiveUserBody, response: Response, userId: str = Depends(require_authenticated_actor_id), db: Session = Depends(get_db)) -> dict[str, Any]:
    actor = _actor(db, userId)
    selected = db.get(AppUser, body.userId)
    if selected is None or selected.stat != "active":
        raise HTTPException(status_code=404, detail="target user not found")
    db.add(ActLog(userId=selected.userId, actorKind="user", actorId=actor.userId, action="update", targetKind="user", targetId=selected.userId))
    db.commit()
    settings = get_settings()
    response.set_cookie(key=settings.auth_cookie_name, value=create_session_token(selected.userId, actor_user_id=actor.userId), max_age=settings.auth_session_hours * 3600, httponly=True, secure=settings.auth_cookie_secure, samesite="lax", path="/")
    return {"ok": True, "data": {"actorUserId": actor.userId, "activeUser": _public(selected), "switchedAt": nowIso()}}
