from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.server.config import Settings, get_settings
from app.server.new_core.models import PushSubscription

logger = logging.getLogger(__name__)


def push_configured(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return bool(
        settings.pwa_push_enabled
        and settings.pwa_push_vapid_public_key.strip()
        and settings.pwa_push_vapid_private_key.strip()
        and settings.pwa_push_vapid_subject.strip()
    )


def send_web_push(
    db: Session,
    *,
    user_id: str,
    title: str,
    content: str,
    evt_id: str | None = None,
    settings: Settings | None = None,
) -> tuple[bool, str | None]:
    settings = settings or get_settings()
    if not push_configured(settings):
        return False, "browser push is not configured"
    rows = db.scalars(
        select(PushSubscription).where(PushSubscription.userId == user_id)
    ).all()
    if not rows:
        return False, "browser push is not subscribed"
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        return False, "browser push dependency is unavailable"

    payload: dict[str, Any] = {
        "title": title,
        "body": content,
        "tag": f"smartcore-{evt_id or 'notice'}",
        "url": "/work/overview",
    }
    sent = 0
    for row in rows:
        subscription = {
            "endpoint": row.endpoint,
            "keys": {"p256dh": row.p256dh, "auth": row.auth},
        }
        try:
            webpush(
                subscription_info=subscription,
                data=json.dumps(payload, ensure_ascii=False),
                vapid_private_key=settings.pwa_push_vapid_private_key,
                vapid_claims={"sub": settings.pwa_push_vapid_subject},
                ttl=3600,
            )
            sent += 1
        except WebPushException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in {404, 410}:
                db.delete(row)
            logger.warning("browser push failed status=%s", status or "unknown")
        except Exception:
            logger.exception("browser push failed")
    if sent:
        return True, None
    return False, "all browser push deliveries failed"
