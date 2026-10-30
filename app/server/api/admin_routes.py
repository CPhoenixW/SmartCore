from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.server.agent.usage import legacy_agent_route_readiness
from app.server.auth.security import (
    require_authenticated_actor_id,
    switch_active_browser_user,
)
from app.server.db.session import get_db
from app.server.new_core.models import (
    ActLog,
    AgentRouteUsage,
    AppUser,
    nowIso,
)

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
def activeUser(body: ActiveUserBody, request: Request, userId: str = Depends(require_authenticated_actor_id), db: Session = Depends(get_db)) -> dict[str, Any]:
    actor = _actor(db, userId)
    selected = db.get(AppUser, body.userId)
    if selected is None or selected.stat != "active":
        raise HTTPException(status_code=404, detail="target user not found")
    db.add(ActLog(userId=selected.userId, actorKind="user", actorId=actor.userId, action="update", targetKind="user", targetId=selected.userId))
    db.commit()
    switch_active_browser_user(request, db, selected.userId)
    return {"ok": True, "data": {"actorUserId": actor.userId, "activeUser": _public(selected), "switchedAt": nowIso()}}


@router.get("/agentRouteUsage")
def agentRouteUsage(
    actorId: str = Depends(require_authenticated_actor_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _actor(db, actorId)
    rows = db.scalars(
        select(AgentRouteUsage).order_by(
            AgentRouteUsage.compatibility.desc(),
            AgentRouteUsage.lastCalledAt.desc(),
        )
    ).all()
    return {
        "ok": True,
        "data": [
            {
                "method": row.method,
                "path": row.path,
                "endpoint": row.endpoint,
                "compatibility": row.compatibility,
                "callCount": row.callCount,
                "successCount": row.successCount,
                "clientErrorCount": row.clientErrorCount,
                "serverErrorCount": row.serverErrorCount,
                "firstCalledAt": row.firstCalledAt,
                "lastCalledAt": row.lastCalledAt,
                "lastStatusCode": row.lastStatusCode,
            }
            for row in rows
        ],
    }


@router.get("/agentRouteCompatibility")
def agentRouteCompatibility(
    actorId: str = Depends(require_authenticated_actor_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _actor(db, actorId)
    return {"ok": True, "data": legacy_agent_route_readiness(db)}
