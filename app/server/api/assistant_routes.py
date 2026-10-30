from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.server.agent.scope import issue_agent_scope
from app.server.auth.security import require_authenticated_user_id
from app.server.config import Settings, get_settings

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


class AssistantMessageBody(BaseModel):
    text: str = Field(min_length=1, max_length=12_000)
    sessionId: str | None = Field(default=None, min_length=1, max_length=160)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)


def _query_endpoint(endpoint: str) -> str:
    endpoint = endpoint.rstrip("/")
    if endpoint.endswith("/events"):
        return endpoint[:-7] + "/query"
    if endpoint.endswith("/query"):
        return endpoint
    return endpoint + "/api/smartcore/query"


def _stream_endpoint(endpoint: str) -> str:
    endpoint = endpoint.rstrip("/")
    if endpoint.endswith("/events"):
        return endpoint[:-7] + "/stream"
    if endpoint.endswith("/query"):
        return endpoint[:-6] + "/stream"
    return endpoint + "/api/smartcore/stream"


def _event_context(body: AssistantMessageBody, user_id: str, settings: Settings) -> dict[str, Any]:
    timezone_name = (body.timezone or settings.daily_summary_timezone or "Asia/Shanghai").strip()
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(status_code=422, detail="timezone must be a valid IANA name") from exc
    now = datetime.now(timezone).replace(microsecond=0)
    return {
        "event_id": f"web-assistant-{user_id}-{uuid4().hex}",
        "source": "web",
        "event_type": "assistant_message",
        "userId": user_id,
        "conversationId": body.sessionId or f"pwa-{user_id}",
        "text": body.text.strip(),
        "timezone": timezone_name,
        "serverNow": now.isoformat(),
        "agentScope": issue_agent_scope(userId=user_id, purpose="web", ttl_seconds=900),
    }


def _sse(event: dict[str, Any]) -> str:
    import json

    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _stream_dsh(
    event: dict[str, Any],
    *,
    endpoint: str,
    token: str,
) -> Iterator[str]:
    # The first status is intentionally local: it is visible even while the
    # bridge is opening a model session, which is the important perceived-
    # latency part of a Grok-style interaction.
    yield _sse({"type": "status", "phase": "thinking", "message": "我先理解一下你的请求…"})
    try:
        with httpx.stream(
            "POST",
            _stream_endpoint(endpoint),
            json=event,
            headers={"Authorization": f"Bearer {token}"},
            timeout=httpx.Timeout(650.0, read=None),
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if not raw:
                    continue
                try:
                    import json

                    payload = json.loads(raw)
                except ValueError:
                    continue
                if not isinstance(payload, dict):
                    continue
                event_type = payload.get("type")
                if event_type in {"status", "message", "tool", "done", "error"}:
                    yield _sse(payload)
    except (httpx.HTTPError, ValueError):
        yield _sse({"type": "error", "message": "助手暂时不可用，请稍后重试。"})
    finally:
        yield _sse({"type": "end"})


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
    event = _event_context(body, user_id, settings)
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


@router.post("/stream")
def assistant_stream(
    body: AssistantMessageBody,
    user_id: str = Depends(require_authenticated_user_id),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    endpoint = settings.assistant_events_endpoint
    token = settings.assistant_events_token
    if not endpoint or not token:
        raise HTTPException(status_code=503, detail="DSH assistant is unavailable")
    event = _event_context(body, user_id, settings)
    return StreamingResponse(
        _stream_dsh(event, endpoint=endpoint, token=token),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
