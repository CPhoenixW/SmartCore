from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import crud
from app.db.session import get_db
from app.feishu.client import FeishuClient
from app.feishu.commands import (
    COMMAND_HELP,
    execute_command,
    extract_message_text,
    parse_command,
)
from app.feishu.security import FeishuSecurityError, parse_event_payload, validate_request_headers

logger = logging.getLogger(__name__)

ALLOWED_EVENT_TYPES = {
    "im.message.receive_v1",
}


class FeishuEventHandler:
    def __init__(
        self,
        settings: Settings,
        client: FeishuClient | None = None,
    ) -> None:
        self.settings = settings
        self.client = client or FeishuClient(
            settings.feishu_app_id,
            settings.feishu_app_secret,
        )

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

        message_id, text = extract_message_text(payload)
        if not text:
            return 200, {"code": 0, "msg": "no text message"}

        command = parse_command(text)
        reply = execute_command(
            db,
            command,
            semester_start=self.settings.semester_start,
        )
        crud.create_message_log(
            db,
            source="feishu",
            external_message_id=message_id,
            raw_content=text,
            parsed_command=command.name,
            reply_status=(
                "ok"
                if command.name != COMMAND_HELP
                or text.strip() in {"帮助", "help", "?"}
                else "help"
            ),
        )

        chat_id = self._resolve_chat_id(payload)
        if chat_id:
            try:
                self.client.send_text(chat_id, reply)
            except Exception:
                logger.exception("failed to send feishu reply")
                return 200, {"code": 0, "msg": "reply failed"}

        return 200, {"code": 0, "msg": "ok"}

    def _resolve_chat_id(self, payload: dict[str, Any]) -> str | None:
        event = payload.get("event")
        if isinstance(event, dict):
            message = event.get("message")
            if isinstance(message, dict):
                chat_id = message.get("chat_id")
                if isinstance(chat_id, str) and chat_id:
                    return chat_id
        if self.settings.feishu_default_chat_id:
            return self.settings.feishu_default_chat_id
        return None


def create_feishu_router(
    handler: FeishuEventHandler | None = None,
) -> APIRouter:
    router = APIRouter()

    def _handler() -> FeishuEventHandler:
        if handler is not None:
            return handler
        settings = get_settings()
        return FeishuEventHandler(settings)

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
