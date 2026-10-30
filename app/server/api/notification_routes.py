from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.server.auth.security import require_authenticated_user_id
from app.server.config import Settings, get_settings
from app.server.db.session import get_db
from app.server.new_core.models import NotifyLog, PushSubscription
from app.server.new_core.push import push_configured

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class PushKeys(BaseModel):
    p256dh: str = Field(min_length=16, max_length=500)
    auth: str = Field(min_length=8, max_length=500)


class PushSubscriptionBody(BaseModel):
    endpoint: str = Field(min_length=20, max_length=2000)
    keys: PushKeys


def _notify_dict(row: NotifyLog) -> dict[str, Any]:
    return {
        "notifyId": row.notifyId,
        "evtId": row.evtId,
        "channel": row.channel,
        "title": row.title,
        "content": row.content,
        "scheduledAt": row.scheduledAt,
        "sentAt": row.sentAt,
        "stat": row.stat,
        "failReason": row.failReason,
    }


@router.get("")
def list_notifications(
    limit: int = 40,
    user_id: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    limit = max(1, min(limit, 100))
    rows = db.scalars(
        select(NotifyLog)
        .where(NotifyLog.userId == user_id)
        .order_by(NotifyLog.scheduledAt.desc())
        .limit(limit)
    ).all()
    return {"ok": True, "data": [_notify_dict(row) for row in rows]}


@router.get("/push/public-key")
def push_public_key(
    _user_id: str = Depends(require_authenticated_user_id),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    return {
        "ok": True,
        "data": {
            "enabled": push_configured(settings),
            "publicKey": settings.pwa_push_vapid_public_key if push_configured(settings) else None,
        },
    }


@router.post("/push-subscription")
def save_push_subscription(
    body: PushSubscriptionBody,
    request: Request,
    user_id: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if not body.endpoint.startswith("https://"):
        raise HTTPException(status_code=422, detail="push endpoint must use HTTPS")
    row = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    if row is None:
        row = PushSubscription(endpoint=body.endpoint, userId=user_id, p256dh=body.keys.p256dh, auth=body.keys.auth)
        db.add(row)
    else:
        row.userId = user_id
        row.p256dh = body.keys.p256dh
        row.auth = body.keys.auth
    row.userAgent = request.headers.get("user-agent", "")[:500] or None
    from app.server.new_core.models import nowIso

    row.updatedAt = nowIso()
    db.commit()
    return {"ok": True, "data": {"subscribed": True}}


@router.delete("/push-subscription")
def delete_push_subscription(
    body: PushSubscriptionBody,
    user_id: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    db.execute(
        delete(PushSubscription).where(
            PushSubscription.endpoint == body.endpoint,
            PushSubscription.userId == user_id,
        )
    )
    db.commit()
    return {"ok": True, "data": {"subscribed": False}}
