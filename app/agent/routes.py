from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.actions.executor import ActionExecutor
from app.config import Settings, get_settings
from app.db.session import get_db
from app.feishu.cards import (
    build_operation_success_card,
    build_query_event_card,
    build_reminder_action_card,
)
from app.feishu.client import FeishuClient

AGENT_TOKEN_HEADER = "X-SmartCore-Agent-Token"

_EVENT_SCHEMA: dict[str, Any] = {
    "event": {
        "event_type": "course|plan|schedule|deadline",
        "title": "text",
        "start_at": "ISO-8601, required except unscheduled schedule/deadline",
        "end_at": "optional ISO-8601",
        "location": "optional text",
        "notes": "optional text",
        "unscheduled": "optional boolean",
    }
}
_SELECTOR_SCHEMA: dict[str, Any] = {
    "selector": {
        "event_type": "course|plan|schedule|deadline",
        "id": "optional SmartCore event id",
        "targets": "optional list of candidate objects returned by query_events",
    }
}

_AGENT_TOOLS: list[dict[str, Any]] = [
    {
        "name": "query_events",
        "endpoint": "/agent/db/query_events",
        "method": "POST",
        "risk": "read",
        "confirmation_required": False,
        "description": "Query SmartCore events by type, status, keyword, and explicit time range.",
        "input_schema": {
            "filter": {
                "event_type": "all|schedule|deadline|plan|course",
                "status": ["pending", "active"],
                "time_range": {"start": "ISO-8601", "end": "ISO-8601"},
                "keyword": "optional text",
                "limit": 50,
            },
            "source_event_id": "optional normalized event id",
            "raw_text": "optional user utterance",
        },
        "output_schema": {
            "ok": "boolean",
            "status": "applied|failed",
            "data": {"events": "list of normalized SmartCore events"},
        },
    },
    {
        "name": "create_event",
        "endpoint": "/agent/db/create_event",
        "method": "POST",
        "risk": "write",
        "confirmation_required": True,
        "description": "Create a SmartCore event through pending-operation confirmation.",
        "input_schema": {
            "payload": _EVENT_SCHEMA,
            "source_event_id": "optional normalized event id",
            "raw_text": "original user utterance",
        },
        "output_schema": {"status": "pending_confirmation|failed", "operation_id": "integer"},
    },
    {
        "name": "update_event",
        "endpoint": "/agent/db/update_event",
        "method": "POST",
        "risk": "write",
        "confirmation_required": True,
        "description": (
            "Update a SmartCore event. Query candidates first when the target is ambiguous."
        ),
        "input_schema": {
            "payload": {
                **_SELECTOR_SCHEMA,
                "patch": "fields to update, such as title/start_at/end_at/notes/status",
            },
            "source_event_id": "optional normalized event id",
            "raw_text": "original user utterance",
        },
        "output_schema": {"status": "pending_confirmation|failed", "operation_id": "integer"},
    },
    {
        "name": "delete_event",
        "endpoint": "/agent/db/delete_event",
        "method": "POST",
        "risk": "destructive",
        "confirmation_required": True,
        "description": (
            "Cancel/delete a SmartCore event through confirmation. "
            "Clarify before destructive actions."
        ),
        "input_schema": {
            "payload": _SELECTOR_SCHEMA,
            "source_event_id": "optional normalized event id",
            "raw_text": "original user utterance",
        },
        "output_schema": {"status": "pending_confirmation|failed", "operation_id": "integer"},
    },
    {
        "name": "send_text",
        "endpoint": "/agent/feedback/send_text",
        "method": "POST",
        "risk": "notify",
        "confirmation_required": False,
        "description": "Send plain text feedback through SmartCore's Feishu client.",
        "input_schema": {"target": {"chat_id": "Feishu chat id"}, "text": "message text"},
        "output_schema": {"ok": "boolean", "result": "Feishu API result"},
    },
    {
        "name": "send_query_result_card",
        "endpoint": "/agent/feedback/send_query_result_card",
        "method": "POST",
        "risk": "notify",
        "confirmation_required": False,
        "description": "Render SmartCore's query-result Feishu card for event lists.",
        "input_schema": {"target": {"chat_id": "Feishu chat id"}, "data": {"events": "list"}},
        "output_schema": {"ok": "boolean", "result": "Feishu API result"},
    },
    {
        "name": "send_operation_success_card",
        "endpoint": "/agent/feedback/send_operation_success_card",
        "method": "POST",
        "risk": "notify",
        "confirmation_required": False,
        "description": "Render SmartCore's operation-success Feishu card.",
        "input_schema": {
            "target": {"chat_id": "Feishu chat id"},
            "data": {
                "action_name": "create_event|update_event|delete_event",
                "payload": "action payload",
            },
        },
        "output_schema": {"ok": "boolean", "result": "Feishu API result"},
    },
    {
        "name": "send_reminder_card",
        "endpoint": "/agent/feedback/send_reminder_card",
        "method": "POST",
        "risk": "notify",
        "confirmation_required": False,
        "description": "Render an actionable reminder card whose buttons round-trip to OpenClaw.",
        "input_schema": {
            "target": {"chat_id": "Feishu chat id"},
            "data": {
                "title": "event title",
                "event_type": "course|plan|schedule|deadline",
                "scheduled_label": "display time label",
                "minutes_until": "optional integer",
                "notes": "optional text",
                "event_id": "optional SmartCore event id",
            },
        },
        "output_schema": {"ok": "boolean", "result": "Feishu API result"},
    },
]


class AgentActionRequest(BaseModel):
    payload: dict[str, Any]
    source_event_id: str | None = None
    raw_text: str = ""


class QueryEventsRequest(BaseModel):
    filter: dict[str, Any]
    source_event_id: str | None = None
    raw_text: str = ""


class FeedbackTarget(BaseModel):
    chat_id: str


class SendTextRequest(BaseModel):
    target: FeedbackTarget
    text: str


class QueryResultCardData(BaseModel):
    events: list[dict[str, Any]]


class SendQueryResultCardRequest(BaseModel):
    target: FeedbackTarget
    data: QueryResultCardData


class OperationSuccessCardData(BaseModel):
    action_name: str
    payload: dict[str, Any]


class SendOperationSuccessCardRequest(BaseModel):
    target: FeedbackTarget
    data: OperationSuccessCardData


class ReminderCardData(BaseModel):
    title: str
    event_type: str
    scheduled_label: str | None = None
    minutes_until: int | None = None
    notes: str | None = None
    event_id: str | int | None = None


class SendReminderCardRequest(BaseModel):
    target: FeedbackTarget
    data: ReminderCardData


def _normalize_query_filter(filter_payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(filter_payload)
    if "time_range" not in normalized:
        start = normalized.pop("start_time", None)
        end = normalized.pop("end_time", None)
        if start or end:
            normalized["time_range"] = {"start": start, "end": end}
    return normalized


def require_agent_token(
    settings: Settings = Depends(get_settings),
    x_smartcore_agent_token: str | None = Header(default=None, alias=AGENT_TOKEN_HEADER),
) -> None:
    expected = settings.agent_api_token
    if not expected:
        return
    if x_smartcore_agent_token != expected:
        raise HTTPException(status_code=401, detail="invalid or missing agent token")


def create_agent_router() -> APIRouter:
    router = APIRouter(prefix="/agent", tags=["agent"])

    @router.get("/tools", dependencies=[Depends(require_agent_token)])
    def list_tools() -> dict[str, list[dict[str, Any]]]:
        return {"tools": _AGENT_TOOLS}

    @router.post("/db/query_events", dependencies=[Depends(require_agent_token)])
    def query_events(
        body: QueryEventsRequest,
        db: Session = Depends(get_db),
    ) -> dict[str, Any]:
        action = {
            "action": "query_event",
            "source": "openclaw",
            "raw_text": body.raw_text,
            "payload": {"filter": _normalize_query_filter(body.filter)},
        }
        if body.source_event_id:
            action["source_event_id"] = body.source_event_id
        return ActionExecutor(db).execute(action)

    def _execute_agent_action(
        action_name: str,
        body: AgentActionRequest,
        db: Session,
    ) -> dict[str, Any]:
        action = {
            "action": action_name,
            "source": "openclaw",
            "raw_text": body.raw_text,
            "payload": body.payload,
        }
        if body.source_event_id:
            action["source_event_id"] = body.source_event_id
        return ActionExecutor(db).execute(action)

    @router.post("/db/create_event", dependencies=[Depends(require_agent_token)])
    def create_event(
        body: AgentActionRequest,
        db: Session = Depends(get_db),
    ) -> dict[str, Any]:
        return _execute_agent_action("create_event", body, db)

    @router.post("/db/update_event", dependencies=[Depends(require_agent_token)])
    def update_event(
        body: AgentActionRequest,
        db: Session = Depends(get_db),
    ) -> dict[str, Any]:
        return _execute_agent_action("update_event", body, db)

    @router.post("/db/delete_event", dependencies=[Depends(require_agent_token)])
    def delete_event(
        body: AgentActionRequest,
        db: Session = Depends(get_db),
    ) -> dict[str, Any]:
        return _execute_agent_action("delete_event", body, db)

    @router.post("/feedback/send_text", dependencies=[Depends(require_agent_token)])
    def send_text(
        body: SendTextRequest,
        settings: Settings = Depends(get_settings),
    ) -> dict[str, Any]:
        client = FeishuClient(settings.feishu_app_id, settings.feishu_app_secret)
        result = client.send_text(body.target.chat_id, body.text)
        return {"ok": True, "result": result}

    @router.post(
        "/feedback/send_query_result_card",
        dependencies=[Depends(require_agent_token)],
    )
    def send_query_result_card(
        body: SendQueryResultCardRequest,
        settings: Settings = Depends(get_settings),
    ) -> dict[str, Any]:
        card = build_query_event_card(body.data.events)
        client = FeishuClient(settings.feishu_app_id, settings.feishu_app_secret)
        result = client.send_interactive_card(body.target.chat_id, card=card)
        return {"ok": True, "result": result}

    @router.post(
        "/feedback/send_operation_success_card",
        dependencies=[Depends(require_agent_token)],
    )
    def send_operation_success_card(
        body: SendOperationSuccessCardRequest,
        settings: Settings = Depends(get_settings),
    ) -> dict[str, Any]:
        card = build_operation_success_card(
            action_name=body.data.action_name,
            payload=body.data.payload,
        )
        client = FeishuClient(settings.feishu_app_id, settings.feishu_app_secret)
        result = client.send_interactive_card(body.target.chat_id, card=card)
        return {"ok": True, "result": result}

    @router.post(
        "/feedback/send_reminder_card",
        dependencies=[Depends(require_agent_token)],
    )
    def send_reminder_card(
        body: SendReminderCardRequest,
        settings: Settings = Depends(get_settings),
    ) -> dict[str, Any]:
        card = build_reminder_action_card(
            title=body.data.title,
            event_type=body.data.event_type,
            scheduled_label=body.data.scheduled_label,
            minutes_until=body.data.minutes_until,
            notes=body.data.notes,
            event_id=body.data.event_id,
        )
        client = FeishuClient(settings.feishu_app_id, settings.feishu_app_secret)
        result = client.send_interactive_card(body.target.chat_id, card=card)
        return {"ok": True, "result": result}

    return router
