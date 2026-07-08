from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.agent.routes import (
    _AGENT_TOOLS,
    _done,
    _failed,
    _getFeishuClient,
    _resolveReceiveId,
    requireAgentToken,
)
from app.config import Settings, get_settings
from app.feishu.cards import (
    build_message_card,
    build_operation_success_card,
    build_query_result_card,
    build_reminder_card,
    normalize_card,
)
from app.feishu.client import FeishuAPIError


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


def _resolve_target(body: dict[str, Any], settings: Settings) -> str | None:
    for key in ("openId", "open_id", "userId", "user_id"):
        value = body.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return _resolveReceiveId(body, settings)


def _send_card(
    body: dict[str, Any],
    card: dict[str, Any],
    settings: Settings,
) -> dict[str, Any]:
    receive_id = _resolve_target(body, settings)
    if not receive_id:
        return _failed(["receiveId/chatId required or configure FEISHU_DEFAULT_CHAT_ID"])
    client = _getFeishuClient(settings)
    if client is None:
        return _failed(["feishu not configured"])
    try:
        normalized = normalize_card(card)
        response = client.send_interactive_card(
            receive_id,
            normalized,
            receive_id_type=_receive_id_type(body),
        )
        return _done(
            {
                "message": response.get("data") or response,
                "receiveId": receive_id,
                "receiveIdType": _receive_id_type(body),
                "msgType": "interactive",
            }
        )
    except (ValueError, FeishuAPIError) as exc:
        return _failed([str(exc)])


def createFeedbackRouter() -> APIRouter:
    ensure_feedback_tools()
    router = APIRouter(prefix="/agent", tags=["agent-feedback"])
    protected = [Depends(requireAgentToken)]

    @router.post("/sendCard", dependencies=protected)
    @router.post("/feedback/send_card", dependencies=protected)
    def send_card(
        body: dict[str, Any],
        settings: Settings = Depends(get_settings),
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
        return _send_card(body, card, settings)

    @router.post("/feedback/send_query_result_card", dependencies=protected)
    def send_query_result_card(
        body: dict[str, Any],
        settings: Settings = Depends(get_settings),
    ) -> dict[str, Any]:
        items = body.get("items") or body.get("events") or body.get("results") or []
        if isinstance(items, dict):
            nested = items.get("items") or items.get("events") or items.get("results")
            items = nested if isinstance(nested, list) else [items]
        if not isinstance(items, list):
            return _failed(["items/events/results must be an array"])
        card = build_query_result_card(
            title=str(body.get("title") or "查询结果"),
            summary=str(body.get("summary") or body.get("content") or "").strip() or None,
            items=[item for item in items if isinstance(item, dict)],
            empty_text=str(body.get("emptyText") or body.get("empty_text") or "没有找到匹配的事项。"),
        )
        return _send_card(body, card, settings)

    @router.post("/feedback/send_operation_success_card", dependencies=protected)
    def send_operation_success_card(
        body: dict[str, Any],
        settings: Settings = Depends(get_settings),
    ) -> dict[str, Any]:
        event = body.get("event") or body.get("data")
        if not isinstance(event, dict):
            event = None
        card = build_operation_success_card(
            title=str(body.get("title") or "操作成功"),
            content=str(body.get("content") or body.get("message") or "").strip() or None,
            operation=str(body.get("operation") or body.get("action") or "").strip() or None,
            event=event,
        )
        return _send_card(body, card, settings)

    @router.post("/feedback/send_reminder_card", dependencies=protected)
    def send_reminder_card(
        body: dict[str, Any],
        settings: Settings = Depends(get_settings),
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
        return _send_card(body, card, settings)

    return router
