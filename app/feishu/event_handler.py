from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.actions.executor import ActionExecutor
from app.config import Settings, get_settings
from app.db import crud
from app.db.models import MessageLog, PendingOperation, PendingOperationStatus
from app.db.session import get_db
from app.feishu.cards import build_pending_operation_card
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
from app.llm.deepseek import DeepSeekOperationParser
from app.operations.parser import (
    CompositeOperationParser,
    ParsedOperation,
    RuleBasedOperationParser,
)
from app.operations.store import create_pending_operation
from app.secretary.rules import DEFAULT_TZ

logger = logging.getLogger(__name__)

ALLOWED_EVENT_TYPES = {
    "im.message.receive_v1",
    "card.action.trigger",
}

_HELP_KEYWORDS = {"帮助", "help", "?"}
_SELECTION_CONFIDENCE_THRESHOLD = 0.85


@dataclass(frozen=True)
class FeishuReply:
    text: str | None = None
    card: dict[str, Any] | None = None
    parsed_command: str | None = None
    reply_status: str | None = None


def build_operation_parser(settings: Settings) -> CompositeOperationParser:
    rule_parser = RuleBasedOperationParser(tz=DEFAULT_TZ)
    llm_parser = None
    if settings.llm_provider == "deepseek" and settings.deepseek_api_key:
        llm_parser = DeepSeekOperationParser(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.llm_model,
            tz=DEFAULT_TZ,
        )
    return CompositeOperationParser(rule_parser=rule_parser, llm_parser=llm_parser)


def _format_query_event_reply(events: list[dict]) -> str:
    lines = ["【事件查询】"]
    if not events:
        lines.append("暂无匹配事件。")
    else:
        for item in events:
            lines.append(f"- {item['title']}")
    return "\n".join(lines)


def _format_confirm_reply(pending: PendingOperation) -> str:
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
        operation_parser: CompositeOperationParser | object | None = None,
    ) -> None:
        self.settings = settings
        self.client = client or FeishuClient(
            settings.feishu_app_id,
            settings.feishu_app_secret,
        )
        self._operation_parser = operation_parser or build_operation_parser(settings)

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
            return self._handle_card_action(payload, db)

        message_id, text = extract_message_text(payload)
        if not text:
            return 200, {"code": 0, "msg": "no text message"}

        if message_id and db.query(MessageLog).filter_by(
            source="feishu",
            external_message_id=message_id,
        ).first():
            return 200, {"code": 0, "msg": "duplicate message ignored"}

        command = parse_command(text)
        reply = self._build_reply(db, command, text)
        parsed_command = (
            reply.parsed_command if reply.parsed_command is not None else command.name
        )
        reply_status = (
            reply.reply_status
            if reply.reply_status is not None
            else (
                "ok"
                if command.name != COMMAND_HELP
                or text.strip() in _HELP_KEYWORDS
                else "help"
            )
        )
        crud.create_message_log(
            db,
            source="feishu",
            external_message_id=message_id,
            raw_content=text,
            parsed_command=parsed_command,
            reply_status=reply_status,
        )

        chat_id = self._resolve_chat_id(payload)
        if chat_id:
            logger.info(
                "feishu message command parsed: message_id=%s command=%s chat_id=%s",
                message_id,
                parsed_command,
                chat_id,
            )
            try:
                if reply.card is not None:
                    self.client.send_interactive_card(chat_id, card=reply.card)
                elif reply.text:
                    self.client.send_text(chat_id, reply.text)
            except Exception:
                logger.exception("failed to send feishu reply")
                return 200, {"code": 0, "msg": "reply failed"}

        return 200, {"code": 0, "msg": "ok"}

    def _handle_card_action(
        self,
        payload: dict[str, Any],
        db: Session,
    ) -> tuple[int, dict[str, Any]]:
        event = payload.get("event")
        if not isinstance(event, dict):
            return 200, {"toast": {"type": "error", "content": "无效卡片回调"}}

        action = event.get("action")
        if not isinstance(action, dict):
            return 200, {"toast": {"type": "error", "content": "无效卡片回调"}}

        value = action.get("value")
        if not isinstance(value, dict):
            return 200, {"toast": {"type": "error", "content": "无效卡片回调"}}

        smartcore_action = value.get("smartcore_action")
        operation_id = value.get("operation_id")
        if not isinstance(operation_id, int):
            return 200, {"toast": {"type": "error", "content": "无效操作编号"}}

        executor = ActionExecutor(db)
        if smartcore_action == "confirm_operation":
            try:
                pending = executor.confirm_and_apply(operation_id)
            except ValueError as exc:
                return 200, {
                    "toast": {
                        "type": "error",
                        "content": _format_confirm_error(operation_id, exc),
                    }
                }
            return 200, {
                "toast": {
                    "type": "success",
                    "content": _format_confirm_reply(pending),
                }
            }

        if smartcore_action == "reject_operation":
            try:
                executor.reject(operation_id)
            except ValueError as exc:
                return 200, {
                    "toast": {
                        "type": "error",
                        "content": _format_reject_error(operation_id, exc),
                    }
                }
            return 200, {
                "toast": {
                    "type": "success",
                    "content": _format_reject_reply(operation_id),
                }
            }

        return 200, {"toast": {"type": "error", "content": "未知卡片操作"}}

    def _build_reply(self, db: Session, command, text: str) -> FeishuReply:
        if command.name in {COMMAND_ADD_ASSIGNMENT, COMMAND_ADD_LIFE_EVENT}:
            return self._create_pending_operation_reply(db, text)
        if command.name == COMMAND_CONFIRM_OPERATION:
            return FeishuReply(text=self._confirm_operation_reply(db, command.args))
        if command.name == COMMAND_REJECT_OPERATION:
            return FeishuReply(text=self._reject_operation_reply(db, command.args))
        if command.name == COMMAND_HELP and text.strip() not in _HELP_KEYWORDS:
            return self._try_free_form_operation_reply(db, text)
        return FeishuReply(
            text=execute_command(
                db,
                command,
                semester_start=self.settings.semester_start,
            )
        )

    def _try_free_form_operation_reply(self, db: Session, text: str) -> FeishuReply:
        try:
            parsed = self._operation_parser.parse(text, source="feishu")
        except ValueError as exc:
            logger.warning("free-form operation parsing failed: text=%r error=%s", text, exc)
            return FeishuReply(
                text=execute_command(
                    db,
                    parse_command("帮助"),
                    semester_start=self.settings.semester_start,
                )
            )
        if self._supports_two_stage_selection(parsed):
            return self._two_stage_event_reply(db, text, parsed)
        if parsed.action_name == "query_event":
            return self._query_event_reply(db, parsed)
        return self._pending_operation_card_reply(db, parsed)

    def _supports_two_stage_selection(self, parsed: ParsedOperation) -> bool:
        return parsed.action_name in {
            "query_event",
            "update_event",
            "delete_event",
        } and hasattr(self._operation_parser, "select_candidates")

    def _two_stage_event_reply(
        self,
        db: Session,
        text: str,
        parsed: ParsedOperation,
    ) -> FeishuReply:
        candidates = ActionExecutor(db).query_events(parsed.payload)
        selection = self._operation_parser.select_candidates(
            raw_text=text,
            parsed=parsed,
            candidates=candidates,
        )
        selected_ids = selection.get("selected_ids") or []
        match_status = selection.get("match_status")
        confidence = float(selection.get("confidence", 0))

        if parsed.action_name == "query_event":
            selected = self._filter_candidates(candidates, selected_ids)
            if match_status == "none" or not selected:
                return FeishuReply(
                    text=_format_query_event_reply([]),
                    parsed_command="query_event",
                    reply_status="ok",
                )
            return FeishuReply(
                text=_format_query_event_reply(selected),
                parsed_command="query_event",
                reply_status="ok",
            )

        if parsed.action_name == "update_event":
            if (
                match_status == "single"
                and len(selected_ids) == 1
                and confidence >= _SELECTION_CONFIDENCE_THRESHOLD
            ):
                resolved = self._resolve_update_payload(
                    parsed,
                    selected_ids[0],
                    candidates,
                )
                return self._pending_operation_card_reply(
                    db,
                    ParsedOperation(
                        source=parsed.source,
                        raw_text=parsed.raw_text,
                        action_name=parsed.action_name,
                        payload=resolved,
                        confidence=parsed.confidence,
                        needs_confirmation=True,
                    ),
                )
            return FeishuReply(
                text=self._format_selection_clarification(
                    parsed.action_name,
                    match_status,
                    selection.get("reason"),
                ),
                parsed_command=parsed.action_name,
                reply_status="ok",
            )

        if parsed.action_name == "delete_event":
            if match_status in {"single", "multiple"} and selected_ids:
                if confidence >= _SELECTION_CONFIDENCE_THRESHOLD:
                    resolved = self._resolve_delete_payload(
                        parsed,
                        selected_ids,
                        candidates,
                    )
                    return self._pending_operation_card_reply(
                        db,
                        ParsedOperation(
                            source=parsed.source,
                            raw_text=parsed.raw_text,
                            action_name=parsed.action_name,
                            payload=resolved,
                            confidence=parsed.confidence,
                            needs_confirmation=True,
                        ),
                    )
            return FeishuReply(
                text=self._format_selection_clarification(
                    parsed.action_name,
                    match_status,
                    selection.get("reason"),
                ),
                parsed_command=parsed.action_name,
                reply_status="ok",
            )

        return self._pending_operation_card_reply(db, parsed)

    @staticmethod
    def _filter_candidates(
        candidates: list[dict],
        selected_ids: list[dict],
    ) -> list[dict]:
        selected_keys = {
            (item.get("event_type"), item.get("id"))
            for item in selected_ids
            if isinstance(item, dict)
        }
        return [
            item
            for item in candidates
            if (item.get("event_type"), item.get("id")) in selected_keys
        ]

    @staticmethod
    def _resolve_update_payload(
        parsed: ParsedOperation,
        target: dict,
        candidates: list[dict],
    ) -> dict:
        payload = dict(parsed.payload)
        payload["selector"] = {
            "event_type": target["event_type"],
            "id": target["id"],
        }
        selected = FeishuEventHandler._filter_candidates(candidates, [target])
        if selected:
            payload["selected_candidates"] = selected
        return payload

    @staticmethod
    def _resolve_delete_payload(
        parsed: ParsedOperation,
        selected_ids: list[dict],
        candidates: list[dict],
    ) -> dict:
        payload = dict(parsed.payload)
        payload["selector"] = {"targets": selected_ids}
        selected = FeishuEventHandler._filter_candidates(candidates, selected_ids)
        if selected:
            payload["selected_candidates"] = selected
        return payload

    @staticmethod
    def _format_selection_clarification(
        action_name: str,
        match_status: str | None,
        reason: str | None,
    ) -> str:
        action_label = {
            "update_event": "修改",
            "delete_event": "删除",
        }.get(action_name, "处理")
        if match_status == "none":
            return f"未找到可{action_label}的事件。"
        if match_status == "ambiguous":
            detail = reason or "目标不够明确"
            return f"无法确定要{action_label}的事件：{detail}，请补充更多信息。"
        detail = reason or "请补充更具体的目标描述"
        return f"无法确定要{action_label}的事件：{detail}。"

    def _query_event_reply(self, db: Session, parsed: ParsedOperation) -> FeishuReply:
        events = ActionExecutor(db).query_events(parsed.payload)
        return FeishuReply(
            text=_format_query_event_reply(events),
            parsed_command="query_event",
            reply_status="ok",
        )

    def _create_pending_operation_reply(self, db: Session, text: str) -> FeishuReply:
        try:
            parsed = self._operation_parser.parse(text, source="feishu")
        except ValueError:
            return FeishuReply(text="无法理解该操作，请检查命令格式。")
        return self._pending_operation_card_reply(db, parsed)

    def _pending_operation_card_reply(
        self,
        db: Session,
        parsed: ParsedOperation,
    ) -> FeishuReply:
        pending = create_pending_operation(db, parsed)
        dashboard_base_url = self.settings.dashboard_base_url or "/dashboard"
        card = build_pending_operation_card(
            operation_id=pending.id,
            raw_text=pending.raw_text,
            action_name=pending.action_name,
            payload=pending.operation_payload,
            dashboard_base_url=dashboard_base_url,
        )
        return FeishuReply(
            card=card,
            parsed_command=pending.action_name,
            reply_status="ok",
        )

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
            context = event.get("context")
            if isinstance(context, dict):
                chat_id = context.get("open_chat_id")
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
