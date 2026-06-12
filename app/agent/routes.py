from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.actions.executor import ActionExecutor
from app.config import Settings, get_settings
from app.db.session import get_db
from app.feishu.cards import build_query_event_card
from app.feishu.client import FeishuClient

AGENT_TOKEN_HEADER = "X-SmartCore-Agent-Token"

_AGENT_TOOLS: list[dict[str, Any]] = [
    {
        "name": "query_events",
        "endpoint": "/agent/db/query_events",
        "method": "POST",
        "risk": "read",
        "confirmation_required": False,
    },
    {
        "name": "send_query_result_card",
        "endpoint": "/agent/feedback/send_query_result_card",
        "method": "POST",
        "risk": "write",
        "confirmation_required": False,
    },
    {
        "name": "send_reminder_card",
        "endpoint": "/agent/feedback/send_reminder_card",
        "method": "POST",
        "risk": "write",
        "confirmation_required": False,
    },
]


class QueryEventsRequest(BaseModel):
    filter: dict[str, Any]
    source_event_id: str | None = None
    raw_text: str = ""


class FeedbackTarget(BaseModel):
    chat_id: str


class QueryResultCardData(BaseModel):
    events: list[dict[str, Any]]


class SendQueryResultCardRequest(BaseModel):
    target: FeedbackTarget
    data: QueryResultCardData


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

    return router
