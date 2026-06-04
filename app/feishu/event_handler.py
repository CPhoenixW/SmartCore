from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.actions.executor import ActionExecutor
from app.config import Settings, get_settings
from app.db import crud
from app.db.models import PendingOperationStatus
from app.db.session import get_db
from app.feishu.client import FeishuClient
from app.feishu.commands import (
    COMMAND_ADD_ASSIGNMENT,
    COMMAND_ADD_LIFE_EVENT,
    COMMAND_CONFIRM_OPERATION,
    COMMAND_HELP,
    COMMAND_REJECT_OPERATION,
    execute_command,
    extract_message_text,
    parse_command,
)
from app.feishu.security import FeishuSecurityError, parse_event_payload, validate_request_headers
from app.operations.parser import RuleBasedOperationParser
from app.operations.store import create_pending_operation
from app.secretary.rules import DEFAULT_TZ

logger = logging.getLogger(__name__)

ALLOWED_EVENT_TYPES = {
    "im.message.receive_v1",
}


def _format_pending_reply(pending_id: int) -> str:
    return (
        f"待确认操作 #{pending_id}\n"
        f"请回复：确认 {pending_id} / 拒绝 {pending_id}"
    )


def _format_confirm_reply(pending) -> str:
    if pending.status == PendingOperationStatus.FAILED.value:
        return f"执行失败：{pending.error_message or '未知错误'}"
    title = pending.operation_payload.get("fields", {}).get("title", "")
    if title:
        return f"已确认并执行：{title}"
    return "已确认并执行"


def _format_confirm_error(operation_id: int, exc: ValueError) -> str:
    message = str(exc)
    if "not found" in message:
        return f"未找到待确认操作 #{operation_id}"
    if "is not pending" in message:
        return f"无法确认操作 #{operation_id}：该操作已处理或已失效"
    return f"无法确认操作 #{operation_id}：{message}"


def _format_reject_reply(operation_id: int) -> str:
    return f"已拒绝待确认操作 #{operation_id}"


def _format_reject_error(operation_id: int, exc: ValueError) -> str:
    message = str(exc)
    if "not found" in message:
        return f"未找到待确认操作 #{operation_id}"
    if "is not pending" in message:
        return f"无法拒绝操作 #{operation_id}：该操作已处理或已失效"
    return f"无法拒绝操作 #{operation_id}：{message}"


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
        self._operation_parser = RuleBasedOperationParser(tz=DEFAULT_TZ)

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
        reply = self._build_reply(db, command, text)
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
            logger.info(
                "feishu message command parsed: message_id=%s command=%s chat_id=%s",
                message_id,
                command.name,
                chat_id,
            )
            try:
                self.client.send_text(chat_id, reply)
            except Exception:
                logger.exception("failed to send feishu reply")
                return 200, {"code": 0, "msg": "reply failed"}

        return 200, {"code": 0, "msg": "ok"}

    def _build_reply(self, db: Session, command, text: str) -> str:
        if command.name in {COMMAND_ADD_ASSIGNMENT, COMMAND_ADD_LIFE_EVENT}:
            return self._create_pending_operation_reply(db, text)
        if command.name == COMMAND_CONFIRM_OPERATION:
            return self._confirm_operation_reply(db, command.args)
        if command.name == COMMAND_REJECT_OPERATION:
            return self._reject_operation_reply(db, command.args)
        return execute_command(
            db,
            command,
            semester_start=self.settings.semester_start,
        )

    def _create_pending_operation_reply(self, db: Session, text: str) -> str:
        try:
            parsed = self._operation_parser.parse(text, source="feishu")
        except ValueError:
            return "无法理解该操作，请检查命令格式。"
        pending = create_pending_operation(db, parsed)
        return _format_pending_reply(pending.id)

    def _confirm_operation_reply(self, db: Session, operation_id_text: str) -> str:
        try:
            operation_id = int(operation_id_text.strip())
        except ValueError:
            return f"无法确认：操作编号无效（{operation_id_text}）"

        executor = ActionExecutor(db)
        try:
            pending = executor.confirm_and_apply(operation_id)
        except ValueError as exc:
            return _format_confirm_error(operation_id, exc)
        return _format_confirm_reply(pending)

    def _reject_operation_reply(self, db: Session, operation_id_text: str) -> str:
        try:
            operation_id = int(operation_id_text.strip())
        except ValueError:
            return f"无法拒绝：操作编号无效（{operation_id_text}）"

        executor = ActionExecutor(db)
        try:
            executor.reject(operation_id)
        except ValueError as exc:
            return _format_reject_error(operation_id, exc)
        return _format_reject_reply(operation_id)

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
    cached_handler: FeishuEventHandler | None = handler

    def _handler() -> FeishuEventHandler:
        nonlocal cached_handler
        if cached_handler is not None:
            return cached_handler
        settings = get_settings()
        cached_handler = FeishuEventHandler(settings)
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
