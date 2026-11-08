from __future__ import annotations

import base64
import json
import logging
from typing import Any
from urllib.parse import urlsplit

import requests
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


def uses_push_relay(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme == "https" and parts.hostname == "fcm.googleapis.com"


class FcmRelaySession(requests.Session):
    """Send Chrome push requests through the Cloudflare Worker."""

    def __init__(self, relay_url: str, relay_token: str):
        super().__init__()
        self._relay_url = relay_url.strip()
        self._relay_token = relay_token.strip()

    def post(self, url, data=None, headers=None, timeout=None, **kwargs):
        if not uses_push_relay(str(url)):
            return super().post(url, data=data, headers=headers, timeout=timeout, **kwargs)
        raw = data if isinstance(data, (bytes, bytearray)) else str(data or "").encode()
        forwarded = {str(key): str(value) for key, value in dict(headers or {}).items()}
        return requests.post(
            self._relay_url,
            json={
                "url": str(url),
                "headers": forwarded,
                "body": base64.b64encode(bytes(raw)).decode("ascii"),
            },
            headers={
                "Authorization": f"Bearer {self._relay_token}",
                "User-Agent": "SmartCorePush/1.0",
            },
            timeout=timeout,
        )


def push_requests_session(settings: Settings) -> FcmRelaySession | None:
    url = settings.pwa_push_relay_url.strip()
    token = settings.pwa_push_relay_token.strip()
    if not url or not token:
        return None
    return FcmRelaySession(url, token)


def send_web_push(
    db: Session,
    *,
    user_id: str,
    title: str,
    content: str,
    evt_id: str | None = None,
    url: str | None = None,
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

    target = str(url or "/work/overview").strip() or "/work/overview"
    if not target.startswith("/"):
        target = "/work/overview"
    payload: dict[str, Any] = {
        "title": title,
        "body": content,
        "tag": f"smartcore-{evt_id or 'notice'}",
        "url": target,
    }
    session = push_requests_session(settings)
    sent = 0
    for row in rows:
        subscription = {
            "endpoint": row.endpoint,
            "keys": {"p256dh": row.p256dh, "auth": row.auth},
        }
        try:
            response = webpush(
                subscription_info=subscription,
                data=json.dumps(payload, ensure_ascii=False),
                vapid_private_key=settings.pwa_push_vapid_private_key,
                vapid_claims={"sub": settings.pwa_push_vapid_subject},
                timeout=settings.pwa_push_timeout_seconds,
                ttl=3600,
                requests_session=session,
            )
            provider_status = getattr(response, "status_code", None)
            if provider_status is not None and not 200 <= int(provider_status) < 300:
                logger.warning("browser push provider rejected status=%s", provider_status)
                continue
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
