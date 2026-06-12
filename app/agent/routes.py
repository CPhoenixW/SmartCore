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

_AGENT_TOOLS: list[dict[str, Any]] = [
    {
        "name": "query_events",
        "endpoint": "/agent/db/query_events",
        "method": "POST",
        "risk": "read",
        "confirmation_required": False,
        "description": "Query SmartCore events by type, status, keyword, and time range.",
        "input_schema": {
            "filter": {
                "event_type": "all|schedule|deadline|plan|course",
                "status": ["pending", "active"],
                "time_range": {"start": "ISO-8601", "end": "ISO-8601"},
                "keyword": "optional text",
                "limit": 50,
            }
        },
    },
    {
        "name": "create_event",
        "endpoint": "/agent/db/create_event",
        "method": "POST",
        "risk": "write",
        "confirmation_required": True,
    },
    {
        "name": "update_event",
        "endpoint": "/agent/db/update_event",
        "method": "POST",
        "risk": "write",
        "confirmation_required": True,
    },
    {
        "name": "delete_event",
        "endpoint": "/agent/db/delete_event",
        "method": "POST",
        "risk": "destructive",
        "confirmation_required": True,
    },
    {
        "name": "send_text",
        "endpoint": "/agent/feedback/send_text",
        "method": "POST",
        "risk": "notify",
        "confirmation_required": False,
    },
    {
        "name": "send_query_result_card",
        "endpoint": "/agent/feedback/send_query_result_card",
        "method": "POST",
        "risk": "notify",
        "confirmation_required": False,
    },
    {
        "name": "send_operation_success_card",
        "endpoint": "/agent/feedback/send_operation_success_card",
        "method": "POST",
        "risk": "notify",
        "confirmation_required": False,
    },
    {
        "name": "send_reminder_card",
        "endpoint": "/agent/feedback/send_reminder_card",
        "method": "POST",
        "risk": "notify",
        "confirmation_required": False,
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
            "payload": {"filter": body.filter},
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
