from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.server.agent.scope import issue_agent_scope
from app.server.auth.security import require_authenticated_user_id
from app.server.config import Settings, get_settings
from app.server.db.session import get_db
from app.server.new_core.assistant_history import (
    PreparedAssistantRequest,
    complete_response,
    conversation_dict,
    fail_response,
    get_conversation,
    get_primary_conversation,
    list_conversations,
    prepare_request,
    search_messages,
)

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


class AssistantMessageBody(BaseModel):
    text: str = Field(min_length=1, max_length=12_000)
    conversationId: str | None = Field(default=None, min_length=1, max_length=160)
    sessionId: str | None = Field(default=None, min_length=1, max_length=160)
    clientMessageId: str | None = Field(default=None, min_length=1, max_length=120)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)


class AssistantConversationBody(BaseModel):
    title: str | None = Field(default=None, max_length=300)


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


def _conversation_id(body: AssistantMessageBody) -> str | None:
    if body.conversationId and body.sessionId and body.conversationId != body.sessionId:
        raise HTTPException(status_code=422, detail="conversationId and sessionId must match")
    return body.conversationId or body.sessionId


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
        "conversationId": _conversation_id(body) or f"pwa-{user_id}",
        "text": body.text.strip(),
        "timezone": timezone_name,
        "serverNow": now.isoformat(),
        "agentScope": issue_agent_scope(userId=user_id, purpose="web", ttl_seconds=900),
    }


def _history_error(exc: ValueError) -> HTTPException:
    detail = str(exc)
    return HTTPException(status_code=404 if "not found" in detail else 422, detail=detail)


def _prepare_history(
    body: AssistantMessageBody,
    *,
    user_id: str,
    db: Session,
) -> PreparedAssistantRequest:
    try:
        return prepare_request(
            db,
            user_id=user_id,
            conversation_id=_conversation_id(body),
            text=body.text,
            client_message_id=body.clientMessageId,
        )
    except ValueError as exc:
        raise _history_error(exc) from exc


def _sse(event: dict[str, Any]) -> str:
    import json

    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _stream_dsh(
    event: dict[str, Any],
    *,
    endpoint: str,
    token: str,
    history: PreparedAssistantRequest,
    db: Session,
) -> Iterator[str]:
    # The first status is intentionally local: it is visible even while the
    # bridge is opening a model session, which is the important perceived-
    # latency part of a Grok-style interaction.
    yield _sse({"type": "status", "phase": "thinking", "message": "我先理解一下你的请求…"})
    response_parts: list[str] = []
    completed = False
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
                    if event_type == "message" and str(payload.get("text") or "").strip():
                        response_parts.append(str(payload["text"]))
                    if event_type == "done":
                        response_text = str(payload.get("response") or "").strip() or "".join(response_parts).strip()
                        complete_response(db, history, response_text)
                        completed = True
                    if event_type == "error" and not completed:
                        fail_response(db, history, str(payload.get("message") or "助手暂时不可用，请稍后重试。"))
                        completed = True
                    yield _sse(payload)
    except (httpx.HTTPError, ValueError):
        if not completed:
            try:
                fail_response(db, history, "助手暂时不可用，请稍后重试。")
                completed = True
            except Exception:
                db.rollback()
        yield _sse({"type": "error", "message": "助手暂时不可用，请稍后重试。"})
    finally:
        if not completed:
            try:
                if response_parts:
                    complete_response(db, history, "".join(response_parts))
                else:
                    fail_response(db, history, "助手暂时不可用，请稍后重试。")
            except Exception:
                db.rollback()
        yield _sse({"type": "end"})


def _stream_replay(history: PreparedAssistantRequest) -> Iterator[str]:
    yield _sse({"type": "status", "phase": "history", "message": "正在加载历史回答…"})
    yield _sse({"type": "message", "text": history.replay_response or "", "mode": "new"})
    yield _sse(
        {
            "type": "done",
            "sessionId": history.conversation.conversationId,
            "conversationId": history.conversation.conversationId,
            "response": history.replay_response or "",
        }
    )
    yield _sse({"type": "end"})


@router.get("/conversations")
def assistant_conversations(
    q: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=30, ge=1, le=100),
    user_id: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        primary = get_primary_conversation(db, user_id=user_id)
        items = (
            search_messages(
                db,
                user_id=user_id,
                query=q,
                limit=limit,
                conversation_id=primary.conversationId,
            )
            if q
            else list_conversations(db, user_id=user_id, limit=limit)
        )
        db.commit()
    except ValueError as exc:
        raise _history_error(exc) from exc
    return {"ok": True, "data": {"items": items, "query": q or ""}}


@router.post("/conversations")
def create_assistant_conversation(
    body: AssistantConversationBody | None = None,
    user_id: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    # Compatibility endpoint: creating a second chat is no longer supported.
    # Return the owner-scoped primary row so older clients converge safely.
    del body
    row = get_primary_conversation(db, user_id=user_id)
    db.commit()
    return {"ok": True, "data": conversation_dict(row)}


@router.get("/conversations/{conversation_id}")
def read_assistant_conversation(
    conversation_id: str,
    user_id: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    result = get_conversation(db, user_id=user_id, conversation_id=conversation_id)
    if result is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return {"ok": True, "data": result}


@router.delete("/conversations/{conversation_id}")
def archive_assistant_conversation(
    conversation_id: str,
    user_id: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    # A single assistant thread is always available. Keep DELETE as a safe
    # compatibility no-op so an old client cannot make the shared chat vanish.
    row = get_primary_conversation(db, user_id=user_id)
    if conversation_id != row.conversationId:
        raise HTTPException(status_code=404, detail="conversation not found")
    db.commit()
    return {"ok": True, "data": {"conversationId": row.conversationId, "stat": row.stat}}


@router.post("/message")
def assistant_message(
    body: AssistantMessageBody,
    user_id: str = Depends(require_authenticated_user_id),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    endpoint = settings.assistant_events_endpoint
    token = settings.assistant_events_token
    if not endpoint or not token:
        raise HTTPException(status_code=503, detail="DSH assistant is unavailable")
    event = _event_context(body, user_id, settings)
    history = _prepare_history(body, user_id=user_id, db=db)
    event["conversationId"] = history.conversation.conversationId
    db.commit()
    if history.replay_response:
        return {
            "ok": True,
            "data": {
                "sessionId": history.conversation.conversationId,
                "conversationId": history.conversation.conversationId,
                "response": history.replay_response,
            },
            "errors": [],
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
        try:
            fail_response(db, history, "助手暂时不可用，请稍后重试。")
        except Exception:
            db.rollback()
        raise HTTPException(status_code=503, detail="DSH assistant request failed") from exc
    data = payload.get("data") if isinstance(payload, dict) and "data" in payload else payload
    if not isinstance(data, dict) or not data.get("response"):
        try:
            fail_response(db, history, "助手没有返回可显示的答案。")
        except Exception:
            db.rollback()
        raise HTTPException(status_code=503, detail="DSH assistant returned no response")
    complete_response(db, history, str(data["response"]))
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
    db: Session = Depends(get_db),
) -> StreamingResponse:
    endpoint = settings.assistant_events_endpoint
    token = settings.assistant_events_token
    if not endpoint or not token:
        raise HTTPException(status_code=503, detail="DSH assistant is unavailable")
    event = _event_context(body, user_id, settings)
    history = _prepare_history(body, user_id=user_id, db=db)
    event["conversationId"] = history.conversation.conversationId
    db.commit()
    if history.replay_response:
        return StreamingResponse(
            _stream_replay(history),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    return StreamingResponse(
        _stream_dsh(event, endpoint=endpoint, token=token, history=history, db=db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
