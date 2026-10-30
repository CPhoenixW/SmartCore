from __future__ import annotations

from typing import Any
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.server.agent.scope import issue_agent_scope
from app.server.auth.security import require_authenticated_user_id
from app.server.config import Settings, get_settings

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


class AssistantMessageBody(BaseModel):
    text: str = Field(min_length=1, max_length=12_000)
    sessionId: str | None = Field(default=None, min_length=1, max_length=160)


def _query_endpoint(endpoint: str) -> str:
    endpoint = endpoint.rstrip("/")
    if endpoint.endswith("/events"):
        return endpoint[:-7] + "/query"
    if endpoint.endswith("/query"):
        return endpoint
    return endpoint + "/api/smartcore/query"


@router.post("/message")
def assistant_message(
    body: AssistantMessageBody,
    user_id: str = Depends(require_authenticated_user_id),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    endpoint = settings.assistant_events_endpoint
    token = settings.assistant_events_token
    if not endpoint or not token:
        raise HTTPException(status_code=503, detail="DSH assistant is unavailable")
    event = {
        "event_id": f"web-assistant-{user_id}-{uuid4().hex}",
        "source": "web",
        "event_type": "assistant_message",
        "userId": user_id,
        "conversationId": body.sessionId or f"pwa-{user_id}",
        "text": body.text.strip(),
        "agentScope": issue_agent_scope(userId=user_id, purpose="web", ttl_seconds=900),
    }
    try:
        response = httpx.post(
            _query_endpoint(endpoint),
            json=event,
            headers={"Authorization": f"Bearer {token}"},
            timeout=650.0,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="DSH assistant request failed") from exc
    data = payload.get("data") if isinstance(payload, dict) and "data" in payload else payload
    if not isinstance(data, dict) or not data.get("response"):
        raise HTTPException(status_code=503, detail="DSH assistant returned no response")
    return {
        "ok": True,
        "data": {
            "sessionId": data.get("sessionId") or event["conversationId"],
            "response": str(data["response"]),
        },
        "errors": [],
    }
