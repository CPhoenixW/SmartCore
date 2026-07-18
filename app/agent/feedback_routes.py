from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.routes import (
    _AGENT_TOOLS,
    _done,
    _failed,
    requireAgentToken,
)
from app.agent.scope import AgentScope, require_agent_scope
from app.db.session import get_db
from app.feishu.bot_service import runtime
from app.feishu.cards import (
    build_message_card,
    build_operation_success_card,
    build_query_result_card,
    build_reminder_card,
    normalize_card,
)
from app.feishu.client import FeishuAPIError
from app.new_core.models import FeishuBind, FeishuBot


def _schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": True,
    }
    if required:
        result["required"] = required
    return result


_FEEDBACK_TOOLS: list[dict[str, Any]] = [
    {
        "name": "sendFeishuMessageCard",
        "method": "POST",
        "path": "/agent/feedback/send_card",
        "legacyPaths": ["/agent/sendCard"],
        "riskLevel": "external",
        "confirmationRequired": False,
        "description": "Send a Feishu interactive card. Prefer title/content over hand-written card JSON.",
        "inputSchema": _schema(
            {
                "title": {"type": "string"},
                "content": {"type": "string"},
                "template": {
                    "type": "string",
                    "enum": [
                        "blue",
                        "green",
                        "orange",
                        "red",
                        "purple",
                        "grey",
                    ],
                },
                "card": {"type": "object"},
                "receiveId": {"type": "string"},
                "chatId": {"type": "string"},
                "receiveIdType": {
                    "type": "string",
                    "enum": ["chat_id", "open_id", "user_id", "union_id", "email"],
                },
            }
        ),
    },
    {
        "name": "sendFeishuQueryResultCard",
        "method": "POST",
        "path": "/agent/feedback/send_query_result_card",
        "riskLevel": "external",
        "confirmationRequired": False,
        "description": "Render event query results as a SmartCore-owned Feishu card.",
        "inputSchema": _schema(
            {
                "title": {"type": "string"},
                "summary": {"type": "string"},
                "items": {"type": "array", "items": {"type": "object"}},
                "events": {"type": "array", "items": {"type": "object"}},
                "results": {"type": "array", "items": {"type": "object"}},
                "data": {"type": "object"},
                "emptyText": {"type": "string"},
                "receiveId": {"type": "string"},
                "chatId": {"type": "string"},
                "receiveIdType": {"type": "string"},
            }
        ),
    },
    {
        "name": "sendFeishuOperationSuccessCard",
        "method": "POST",
        "path": "/agent/feedback/send_operation_success_card",
        "riskLevel": "external",
        "confirmationRequired": False,
        "description": "Render a successful SmartCore operation as a Feishu card.",
        "inputSchema": _schema(
            {
                "title": {"type": "string"},
                "content": {"type": "string"},
                "message": {"type": "string"},
                "operation": {"type": "string"},
                "event": {"type": "object"},
                "data": {"type": "object"},
                "receiveId": {"type": "string"},
                "chatId": {"type": "string"},
                "receiveIdType": {"type": "string"},
            }
        ),
    },
    {
        "name": "sendFeishuReminderCard",
        "method": "POST",
        "path": "/agent/feedback/send_reminder_card",
        "riskLevel": "external",
        "confirmationRequired": False,
        "description": "Send a reminder card with SmartCore completion and snooze buttons.",
        "inputSchema": _schema(
            {
                "evtId": {"type": "string", "minLength": 1},
                "title": {"type": "string"},
                "content": {"type": "string"},
                "allowDone": {"type": "boolean", "default": True},
                "allowSnooze": {"type": "boolean", "default": True},
                "receiveId": {"type": "string"},
                "chatId": {"type": "string"},
                "receiveIdType": {"type": "string"},
            },
            ["evtId"],
        ),
    },
]


def ensure_feedback_tools() -> None:
    existing = {str(tool.get("name")) for tool in _AGENT_TOOLS}
    for tool in _FEEDBACK_TOOLS:
        if tool["name"] not in existing:
            _AGENT_TOOLS.append(tool)
            existing.add(tool["name"])


def _receive_id_type(body: dict[str, Any]) -> str:
    explicit = body.get("receiveIdType") or body.get("receive_id_type")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    if body.get("openId") or body.get("open_id"):
        return "open_id"
    if body.get("userId") or body.get("user_id"):
        return "user_id"
    return "chat_id"


def _send_card(
    body: dict[str, Any],
    card: dict[str, Any],
    db: Session,
    scope: AgentScope,
) -> dict[str, Any]:
    bot = db.get(FeishuBot, scope.botId)
    binding = db.scalar(select(FeishuBind).where(
        FeishuBind.botId == scope.botId,
        FeishuBind.userId == scope.userId,
        FeishuBind.chatId == scope.chatId,
        FeishuBind.stat == "active",
    ))
    if bot is None or not bot.enabled or binding is None:
        return _failed(["scoped Feishu chat is no longer active"])
    try:
        normalized = normalize_card(card)
        response = runtime(bot).client().send_interactive_card(
            scope.chatId,
            normalized,
            receive_id_type="chat_id",
        )
        return _done(
            {
                "message": response.get("data") or response,
                "receiveId": scope.chatId,
                "receiveIdType": "chat_id",
                "msgType": "interactive",
            }
        )
    except (ValueError, FeishuAPIError) as exc:
        return _failed([str(exc)])


def _send_text(body: dict[str, Any], db: Session, scope: AgentScope) -> dict[str, Any]:
    text = body.get("text")
    if not isinstance(text, str) or not text.strip():
        return _failed(["text required"])
    card = build_message_card(content=text.strip())
    return _send_card(body, card, db, scope)


def _extract_query_items(body: dict[str, Any]) -> list[dict[str, Any]] | None:
    value: Any = body.get("items") or body.get("events") or body.get("results")
    if value is None and isinstance(body.get("data"), dict):
        data = body["data"]
        value = data.get("items") or data.get("events") or data.get("results")
    if value is None:
        return []
    if isinstance(value, dict):
        nested = value.get("items") or value.get("events") or value.get("results")
        value = nested if isinstance(nested, list) else [value]
    if not isinstance(value, list):
        return None
    return [item for item in value if isinstance(item, dict)]


def createFeedbackRouter() -> APIRouter:
    ensure_feedback_tools()
    router = APIRouter(prefix="/agent", tags=["agent-feedback"])
    protected = [Depends(requireAgentToken), Depends(require_agent_scope)]

    @router.get("/tools", dependencies=protected)
    def list_tools() -> dict[str, Any]:
        from app.agent.v2_routes import _enhanced_tools

        now = datetime.now(ZoneInfo("Asia/Shanghai")).replace(microsecond=0)
        tools = _enhanced_tools()
        return {
            "ok": True,
            "stat": "done",
            "data": {
                "version": "2026-07-08-feishu-card-v3",
                "authHeader": "X-SmartCore-Agent-Token",
                "requestContext": {
                    "timezone": "Asia/Shanghai",
                    "now": now.isoformat(),
                },
                "feedbackPolicy": {
                    "default": "Use structured Feishu card tools for user-facing query and operation results.",
                    "rawCardJson": "Optional; SmartCore normalizes Card JSON 2.0 to the interactive message format.",
                },
                "tools": tools,
            },
            "errors": [],
            "tools": tools,
        }

    @router.post("/sendCard", dependencies=protected)
    @router.post("/feedback/send_card", dependencies=protected)
    def send_card(
        body: dict[str, Any],
        db: Session = Depends(get_db),
        scope: AgentScope = Depends(require_agent_scope),
    ) -> dict[str, Any]:
        raw_card = body.get("card")
        if isinstance(raw_card, dict):
            card = raw_card
        else:
            content = body.get("content") or body.get("text") or body.get("message")
            if not isinstance(content, str) or not content.strip():
                return _failed(["card or content required"])
            card = build_message_card(
                title=str(body.get("title") or "SmartCore"),
                content=content.strip(),
                template=str(body.get("template") or "blue"),
            )
        return _send_card(body, card, db, scope)

    @router.post("/sendText", dependencies=protected)
    @router.post("/feedback/send_text", dependencies=protected)
    def send_text(
        body: dict[str, Any],
        db: Session = Depends(get_db),
        scope: AgentScope = Depends(require_agent_scope),
    ) -> dict[str, Any]:
        return _send_text(body, db, scope)

    @router.post("/feedback/send_query_result_card", dependencies=protected)
    def send_query_result_card(
        body: dict[str, Any],
        db: Session = Depends(get_db),
        scope: AgentScope = Depends(require_agent_scope),
    ) -> dict[str, Any]:
        items = _extract_query_items(body)
        if items is None:
            return _failed(["items/events/results must be an array"])
        card = build_query_result_card(
            title=str(body.get("title") or "查询结果"),
            summary=str(body.get("summary") or body.get("content") or "").strip() or None,
            items=items,
            empty_text=str(body.get("emptyText") or body.get("empty_text") or "没有找到匹配的事项。"),
        )
        return _send_card(body, card, db, scope)

    @router.post("/feedback/send_operation_success_card", dependencies=protected)
    def send_operation_success_card(
        body: dict[str, Any],
        db: Session = Depends(get_db),
        scope: AgentScope = Depends(require_agent_scope),
    ) -> dict[str, Any]:
        event = body.get("event") or body.get("data")
        if isinstance(event, dict) and isinstance(event.get("event"), dict):
            event = event["event"]
        if not isinstance(event, dict):
            event = None
        card = build_operation_success_card(
            title=str(body.get("title") or "操作成功"),
            content=str(body.get("content") or body.get("message") or "").strip() or None,
            operation=str(body.get("operation") or body.get("action") or "").strip() or None,
            event=event,
        )
        return _send_card(body, card, db, scope)

    @router.post("/feedback/send_reminder_card", dependencies=protected)
    def send_reminder_card(
        body: dict[str, Any],
        db: Session = Depends(get_db),
        scope: AgentScope = Depends(require_agent_scope),
    ) -> dict[str, Any]:
        evt_id = body.get("evtId") or body.get("eventId")
        if not isinstance(evt_id, str) or not evt_id.strip():
            return _failed(["evtId required"])
        title = str(body.get("title") or "提醒")
        content = str(body.get("content") or body.get("message") or title)
        card = build_reminder_card(
            evt_id=evt_id.strip(),
            title=title,
            content=content,
            allow_done=bool(body.get("allowDone", True)),
            allow_snooze=bool(body.get("allowSnooze", True)),
        )
        return _send_card(body, card, db, scope)

    return router
