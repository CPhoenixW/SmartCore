from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.session import get_db
from app.feishu.commands import extract_message_text, extract_routing_context
from app.feishu.security import FeishuSecurityError, parse_event_payload, validate_request_headers
from app.new_core import crud

logger = logging.getLogger(__name__)
_DEFAULT_TZ = ZoneInfo("Asia/Shanghai")

ALLOWED_EVENT_TYPES = {
    "im.message.receive_v1",
    "card.action.trigger",
}


class FeishuEventHandler:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def handle(
        self,
        body: bytes,
        headers: dict[str, str],
        db: Session,
        *,
        now: float | None = None,
    ) -> tuple[int, dict[str, Any]]:
        body_text = body.decode("utf-8")
        try:
            if self.settings.feishu_encrypt_key:
                validate_request_headers(
                    headers,
                    encrypt_key=self.settings.feishu_encrypt_key,
                    body=body_text,
                    now=now,
                    max_age_seconds=self.settings.feishu_replay_max_age_seconds,
                )
            payload = parse_event_payload(
                body_text,
                encrypt_key=self.settings.feishu_encrypt_key,
                verification_token=self.settings.feishu_verification_token,
            )
        except FeishuSecurityError as exc:
            logger.warning("feishu security validation failed: %s", exc)
            return 403, {"code": 403, "msg": "forbidden"}

        if payload.get("type") == "url_verification":
            return 200, {"challenge": payload.get("challenge", "")}

        event_type = None
        if isinstance(payload.get("header"), dict):
            event_type = payload["header"].get("event_type")
        if event_type and event_type not in ALLOWED_EVENT_TYPES:
            return 200, {"code": 0, "msg": "ignored event type"}

        if event_type == "card.action.trigger":
            handled, response = self._handleSmartcoreReminderAction(payload, db, now=now)
            if handled:
                return 200, response

        if not self.settings.openclaw_events_endpoint:
            return 200, {"code": 0, "msg": "openclaw not configured"}

        if event_type == "card.action.trigger":
            return self._forwardCardAction(payload, db, now=now)
        return self._forwardTextMessage(payload, db, now=now)

    def _openclawHeaders(self) -> dict[str, str] | None:
        token = self.settings.openclaw_events_token
        if not token:
            return None
        return {"Authorization": f"Bearer {token}"}

    def _postOpenclaw(self, event: dict[str, Any]) -> None:
        response = httpx.post(
            self.settings.openclaw_events_endpoint,
            json=event,
            headers=self._openclawHeaders(),
            timeout=10.0,
        )
        if response.is_error:
            raise httpx.HTTPStatusError(
                f"OpenClaw event endpoint returned {response.status_code}",
                request=response.request,
                response=response,
            )

    @staticmethod
    def _timeContext(now: float | None) -> dict[str, Any]:
        now_dt = (
            datetime.fromtimestamp(now, _DEFAULT_TZ)
            if now is not None
            else datetime.now(_DEFAULT_TZ)
        ).replace(microsecond=0)
        offset = now_dt.strftime("%z")
        return {
            "timezone": "Asia/Shanghai",
            "now": now_dt.isoformat(),
            "date": now_dt.date().isoformat(),
            "weekday": now_dt.isoweekday(),
            "utcOffset": f"{offset[:3]}:{offset[3:]}",
            "policy": "Resolve relative dates against this context, then call SmartCore with an absolute ISO 8601 date-time including its UTC offset.",
        }

    def _normalizeMessage(
        self,
        payload: dict[str, Any],
        *,
        message_id: str,
        text: str,
        now: float | None,
    ) -> dict[str, Any]:
        time_context = self._timeContext(now)
        chat, user = extract_routing_context(payload)
        normalized: dict[str, Any] = {
            "eventType": "message",
            "message_id": message_id,
            "text": text,
            "message": {
                "message_id": message_id,
                "text": text,
            },
            "request": time_context,
            "time_context": time_context,
            "timezone": time_context["timezone"],
            "now": time_context["now"],
            "feishu_payload": payload,
        }
        if chat_id := chat.get("chat_id"):
            normalized["chat_id"] = chat_id
        if chat:
            normalized["chat"] = chat
        if user:
            normalized["user"] = user
        return normalized

    def _normalizeCardAction(
        self,
        payload: dict[str, Any],
        *,
        now: float | None,
    ) -> dict[str, Any]:
        time_context = self._timeContext(now)
        event_body = payload.get("event") if isinstance(payload.get("event"), dict) else {}
        context = event_body.get("context") if isinstance(event_body.get("context"), dict) else {}
        chat: dict[str, str] = {}
        if open_chat_id := context.get("open_chat_id"):
            if isinstance(open_chat_id, str) and open_chat_id:
                chat["chat_id"] = open_chat_id
        operator = event_body.get("operator")
        user: dict[str, str] = {}
        if isinstance(operator, dict):
            operator_id = operator.get("operator_id")
            if isinstance(operator_id, dict):
                for key in ("open_id", "union_id", "user_id"):
                    value = operator_id.get(key)
                    if isinstance(value, str) and value:
                        user[key] = value
        normalized: dict[str, Any] = {
            "eventType": "card_action",
            "card_action": {
                "action": event_body.get("action"),
                "context": context,
            },
            "request": time_context,
            "time_context": time_context,
            "timezone": time_context["timezone"],
            "now": time_context["now"],
            "feishu_payload": payload,
        }
        if chat_id := chat.get("chat_id"):
            normalized["chat_id"] = chat_id
        if chat:
            normalized["chat"] = chat
        if user:
            normalized["user"] = user
        return normalized

    def _handleSmartcoreReminderAction(
        self,
        payload: dict[str, Any],
        db: Session,
        *,
        now: float | None,
    ) -> tuple[bool, dict[str, Any]]:
        event_body = payload.get("event") if isinstance(payload.get("event"), dict) else {}
        action = event_body.get("action")
        if not isinstance(action, dict):
            return False, {}
        value = action.get("value")
        if not isinstance(value, dict) or value.get("kind") != "smartcoreReminder":
            return False, {}

        evt_id = value.get("evtId")
        action_name = value.get("action")
        if not isinstance(evt_id, str) or not evt_id:
            return True, {"toast": {"type": "error", "content": "缺少事件 ID"}}
        if action_name == "reminderDone":
            mapped = "done"
        elif action_name == "reminderSnooze10":
            mapped = "snooze10"
        else:
            return True, {"toast": {"type": "error", "content": "未知操作"}}

        now_dt = (
            datetime.fromtimestamp(now, _DEFAULT_TZ)
            if now is not None
            else datetime.now(_DEFAULT_TZ)
        )
        try:
            crud.applyReminderAction(
                db,
                evtId=evt_id,
                action=mapped,
                now=now_dt.isoformat(),
                src="feishu",
            )
        except ValueError:
            return True, {"toast": {"type": "error", "content": "事件不存在或无法更新"}}
        return True, {"toast": {"type": "success", "content": "已更新"}}

    def _forwardTextMessage(
        self,
        payload: dict[str, Any],
        db: Session,
        *,
        now: float | None,
    ) -> tuple[int, dict[str, Any]]:
        message_id, text = extract_message_text(payload)
        if not text:
            return 200, {"code": 0, "msg": "no text message"}

        if message_id and crud.msgLogExists(db, src="feishu", externalId=message_id):
            return 200, {"code": 0, "msg": "duplicate message ignored"}

        normalized = self._normalizeMessage(
            payload,
            message_id=message_id or "",
            text=text,
            now=now,
        )
        stat = "forwarded"
        try:
            self._postOpenclaw(normalized)
        except Exception:
            logger.exception(
                "failed to forward feishu message to openclaw: message_id=%s",
                message_id,
            )
            stat = "forward_failed"

        if message_id:
            crud.createMsgLog(
                db,
                src="feishu",
                externalId=message_id,
                rawText=text,
                intent="openclaw_forward",
                stat=stat,
            )
        return 200, {"code": 0, "msg": "ok"}

    def _forwardCardAction(
        self,
        payload: dict[str, Any],
        db: Session,
        *,
        now: float | None,
    ) -> tuple[int, dict[str, Any]]:
        normalized = self._normalizeCardAction(payload, now=now)
        try:
            self._postOpenclaw(normalized)
        except Exception:
            logger.exception("failed to forward feishu card action to openclaw")
            return 200, {"toast": {"type": "error", "content": "事件转发失败"}}
        return 200, {"code": 0, "msg": "ok"}


def create_feishu_router(handler: FeishuEventHandler | None = None) -> APIRouter:
    router = APIRouter()
    cached_handler: FeishuEventHandler | None = handler

    def _handler() -> FeishuEventHandler:
        nonlocal cached_handler
        if cached_handler is not None:
            return cached_handler
        cached_handler = FeishuEventHandler(get_settings())
        return cached_handler

    @router.post("/feishu/event")
    async def feishu_event(
        request: Request,
        db: Session = Depends(get_db),
    ) -> Response:
        body = await request.body()
        event_handler = _handler()
        status_code, payload = event_handler.handle(body, dict(request.headers), db)
        return Response(
            content=json.dumps(payload, ensure_ascii=False),
            status_code=status_code,
            media_type="application/json",
        )

    return router
