from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.actions.executor import ActionExecutor
from app.actions.normalize import action_from_parsed, ensure_default_query_time_range
from app.actions.reply import format_result_reply
from app.config import Settings, get_settings
from app.db import crud
from app.db.models import MessageLog, PendingOperation, PendingOperationStatus
from app.db.session import get_db
from app.feishu.cards import (
    build_operation_success_card,
    build_pending_operation_card,
    build_query_event_card,
)
from app.feishu.client import FeishuClient
from app.feishu.commands import extract_message_text, format_help_message
from app.feishu.security import FeishuSecurityError, parse_event_payload, validate_request_headers
from app.llm.deepseek import DeepSeekOperationParser
from app.operations.parser import (
    OperationParser,
    ParsedOperation,
)
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
    action_input: dict[str, Any] | None = None
    db_result: dict[str, Any] | None = None


def build_operation_parser(settings: Settings) -> OperationParser | None:
    if settings.llm_provider != "deepseek" or not settings.deepseek_api_key:
        return None
    llm_parser = DeepSeekOperationParser(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.llm_model,
        tz=DEFAULT_TZ,
    )
    return OperationParser(llm_parser)


def _format_confirm_reply(pending: PendingOperation) -> str:
    if pending.status == PendingOperationStatus.FAILED.value:
        return f"执行失败：{pending.error_message or '未知错误'}"
    event = (pending.operation_payload.get("payload") or {}).get("event") or {}
    title = event.get("title", "")
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
        operation_parser: OperationParser | object | None = None,
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

        now_dt = (
            datetime.fromtimestamp(now, DEFAULT_TZ)
            if now is not None
            else datetime.now(DEFAULT_TZ)
        )
        reply = self._handle_text_message(db, text, now_dt=now_dt)
        parsed_command = reply.parsed_command or "unknown"
        reply_status = reply.reply_status or "ok"
        crud.create_message_log(
            db,
            source="feishu",
            external_message_id=message_id,
            raw_content=text,
            parsed_command=parsed_command,
            reply_status=reply_status,
            action_input=reply.action_input,
            db_result=reply.db_result,
        )

        chat_id = self._resolve_chat_id(payload)
        if chat_id:
            logger.info(
                "feishu message parsed: message_id=%s command=%s chat_id=%s",
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

    def _handle_text_message(
        self,
        db: Session,
        text: str,
        *,
        now_dt: datetime,
    ) -> FeishuReply:
        if text.strip() in _HELP_KEYWORDS:
            return FeishuReply(
                text=format_help_message(),
                parsed_command="help",
                reply_status="help",
            )

        if self._operation_parser is None:
            return FeishuReply(
                text="自然语言解析未配置，请设置 LLM_PROVIDER=deepseek 和 DEEPSEEK_API_KEY。",
                parsed_command="help",
                reply_status="help",
            )

        try:
            parsed = self._operation_parser.parse(text, source="feishu", now=now_dt)
        except ValueError as exc:
            logger.warning("operation parsing failed: text=%r error=%s", text, exc)
            return FeishuReply(
                text=format_help_message(),
                parsed_command="help",
                reply_status="help",
            )

        if self._supports_two_stage_selection(parsed):
            return self._two_stage_event_reply(db, text, parsed, now_dt=now_dt)

        action = action_from_parsed(parsed, now=now_dt)
        return self._execute_action_reply(db, action)

    def _execute_action_reply(self, db: Session, action: dict[str, Any]) -> FeishuReply:
        executor = ActionExecutor(db)
        result = executor.execute(action)
        action_name = result.get("action") or action.get("action")

        if result.get("status") == "pending_confirmation" and result.get("operation_id"):
            pending = db.get(PendingOperation, result["operation_id"])
            if pending is not None:
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
                    parsed_command=action_name,
                    reply_status="ok",
                    action_input=action,
                    db_result=result,
                )

        if action_name == "query_event":
            events = (result.get("data") or {}).get("events") or []
            return FeishuReply(
                card=build_query_event_card(events),
                parsed_command=action_name,
                reply_status="ok",
                action_input=action,
                db_result=result,
            )

        return FeishuReply(
            text=format_result_reply(result),
            parsed_command=action_name,
            reply_status="ok",
            action_input=action,
            db_result=result,
        )

    def _query_event_feishu_reply(
        self,
        *,
        query_action: dict[str, Any],
        result: dict[str, Any],
        events: list[dict[str, Any]],
    ) -> FeishuReply:
        return FeishuReply(
            card=build_query_event_card(events),
            parsed_command="query_event",
            reply_status="ok",
            action_input=query_action,
            db_result=result,
        )

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

        context = event.get("context")
        open_message_id = None
        open_chat_id = None
        if isinstance(context, dict):
            raw_message_id = context.get("open_message_id")
            if isinstance(raw_message_id, str) and raw_message_id:
                open_message_id = raw_message_id
            raw_chat_id = context.get("open_chat_id")
            if isinstance(raw_chat_id, str) and raw_chat_id:
                open_chat_id = raw_chat_id

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
            self._delete_card_message(open_message_id)
            if (
                open_chat_id
                and pending.status != PendingOperationStatus.FAILED.value
            ):
                self._send_success_card(open_chat_id, pending)
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
            self._delete_card_message(open_message_id)
            return 200, {
                "toast": {
                    "type": "success",
                    "content": _format_reject_reply(operation_id),
                }
            }

        return 200, {"toast": {"type": "error", "content": "未知卡片操作"}}

    def _delete_card_message(self, open_message_id: str | None) -> None:
        if not open_message_id:
            return
        try:
            self.client.delete_message(open_message_id)
        except Exception:
            logger.exception(
                "failed to delete feishu card message: message_id=%s",
                open_message_id,
            )

    def _send_success_card(self, chat_id: str, pending: PendingOperation) -> None:
        card = build_operation_success_card(
            action_name=pending.action_name,
            payload=pending.operation_payload,
        )
        try:
            self.client.send_interactive_card(chat_id, card=card)
        except Exception:
            logger.exception(
                "failed to send feishu success card: chat_id=%s operation_id=%s",
                chat_id,
                pending.id,
            )

    def _supports_two_stage_selection(self, parsed: ParsedOperation) -> bool:
        if not hasattr(self._operation_parser, "select_candidates"):
            return False
        payload = parsed.payload
        if not isinstance(payload.get("action"), str):
            return False
        inner = payload.get("payload") or {}
        if parsed.action_name == "query_event":
            semantic = inner.get("semantic") or {}
            return bool(semantic.get("target_description"))
        if parsed.action_name in {"update_event", "delete_event"}:
            selector = inner.get("selector") or {}
            if selector.get("id") is not None:
                return False
            return bool(
                selector.get("mode") == "semantic_ref"
                or selector.get("target_description")
                or selector.get("time_range")
            )
        return False

    def _two_stage_event_reply(
        self,
        db: Session,
        text: str,
        parsed: ParsedOperation,
        *,
        now_dt: datetime,
    ) -> FeishuReply:
        query_action = self._build_candidate_query_action(parsed, now_dt=now_dt)
        executor = ActionExecutor(db)
        query_result = executor.execute(query_action)
        candidates = (query_result.get("data") or {}).get("events") or []

        selection = self._operation_parser.select_candidates(
            raw_text=text,
            parsed=parsed,
            candidates=candidates,
        )
        selected_refs = selection.get("selected_refs") or []
        match_status = selection.get("match_status")
        confidence = float(selection.get("confidence", 0))

        if parsed.action_name == "query_event":
            selected = self._filter_candidates_by_ref(candidates, selected_refs)
            if match_status == "none" or not selected:
                result = {
                    "ok": True,
                    "action": "query_event",
                    "status": "applied",
                    "message_code": "EVENTS_FOUND",
                    "data": {"events": []},
                    "debug": query_result.get("debug", {}),
                }
                return self._query_event_feishu_reply(
                    query_action=query_action,
                    result=result,
                    events=[],
                )
            result = {
                "ok": True,
                "action": "query_event",
                "status": "applied",
                "message_code": "EVENTS_FOUND",
                "data": {"events": selected},
                "debug": query_result.get("debug", {}),
            }
            return self._query_event_feishu_reply(
                query_action=query_action,
                result=result,
                events=selected,
            )

        if parsed.action_name == "update_event":
            if (
                match_status == "single"
                and len(selected_refs) == 1
                and confidence >= _SELECTION_CONFIDENCE_THRESHOLD
            ):
                update_action = self._build_ref_action(
                    parsed,
                    selected_refs,
                    query_action,
                    patch=self._extract_patch(parsed),
                )
                return self._execute_action_reply(db, update_action)
            return FeishuReply(
                text=self._format_selection_clarification(
                    parsed.action_name,
                    match_status,
                    selection.get("reason"),
                ),
                parsed_command=parsed.action_name,
                reply_status="ok",
                action_input=query_action,
                db_result=query_result,
            )

        if parsed.action_name == "delete_event":
            if match_status in {"single", "multiple"} and selected_refs:
                if confidence >= _SELECTION_CONFIDENCE_THRESHOLD:
                    delete_action = self._build_ref_action(
                        parsed,
                        selected_refs,
                        query_action,
                        allow_multiple=True,
                    )
                    return self._execute_action_reply(db, delete_action)
            return FeishuReply(
                text=self._format_selection_clarification(
                    parsed.action_name,
                    match_status,
                    selection.get("reason"),
                ),
                parsed_command=parsed.action_name,
                reply_status="ok",
                action_input=query_action,
                db_result=query_result,
            )

        return self._execute_action_reply(db, action_from_parsed(parsed, now=now_dt))

    def _build_candidate_query_action(
        self,
        parsed: ParsedOperation,
        *,
        now_dt: datetime,
    ) -> dict[str, Any]:
        payload = parsed.payload
        inner = payload.get("payload") or {}
        selector = inner.get("selector") or {}
        source_filter = inner.get("filter") if isinstance(inner.get("filter"), dict) else {}

        filter_payload: dict[str, Any] = {
            "event_type": "all",
            "status": ["pending", "active"],
            "limit": selector.get("max_candidates") or source_filter.get("limit") or 50,
        }
        if source_filter.get("time_range"):
            filter_payload["time_range"] = source_filter["time_range"]
        elif selector.get("time_range"):
            filter_payload["time_range"] = selector["time_range"]
        if selector.get("status") == "open":
            filter_payload["status"] = ["pending", "active"]

        action = {
            "action": "query_event",
            "source": parsed.source,
            "raw_text": parsed.raw_text,
            "confidence": parsed.confidence,
            "needs_confirmation": parsed.needs_confirmation,
            "request": {
                "timezone": "Asia/Shanghai",
                "now": now_dt.isoformat(),
            },
            "payload": {"filter": filter_payload},
        }
        return ensure_default_query_time_range(action, now_dt)

    @staticmethod
    def _extract_patch(parsed: ParsedOperation) -> dict[str, Any]:
        payload = parsed.payload
        if isinstance(payload.get("payload"), dict):
            patch = payload["payload"].get("patch")
            if isinstance(patch, dict):
                return patch
        return {}

    def _build_ref_action(
        self,
        parsed: ParsedOperation,
        refs: list[str],
        query_action: dict[str, Any],
        *,
        patch: dict[str, Any] | None = None,
        allow_multiple: bool = False,
    ) -> dict[str, Any]:
        query_filter = (query_action.get("payload") or {}).get("filter") or {}
        selector: dict[str, Any] = {
            "mode": "semantic_ref",
            "refs": refs,
            "filter": {
                "event_type": query_filter.get("event_type", "all"),
            },
        }
        if query_filter.get("time_range"):
            selector["filter"]["time_range"] = query_filter["time_range"]
        if allow_multiple:
            selector["allow_multiple"] = True
        payload: dict[str, Any] = {"selector": selector}
        if patch:
            payload["patch"] = patch
        return {
            "action": parsed.action_name,
            "source": parsed.source,
            "raw_text": parsed.raw_text,
            "payload": payload,
        }

    @staticmethod
    def _filter_candidates_by_ref(
        candidates: list[dict],
        selected_refs: list[str],
    ) -> list[dict]:
        ref_set = set(selected_refs)
        return [item for item in candidates if item.get("ref") in ref_set]

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
