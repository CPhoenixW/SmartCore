from __future__ import annotations

import logging
import mimetypes
from collections.abc import Callable, Iterator
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.server.agent.scope import issue_agent_scope
from app.server.auth.security import require_authenticated_user_id
from app.server.config import Settings, get_settings
from app.server.db.session import get_db
from app.server.new_core import crud
from app.server.new_core.assistant_history import (
    PreparedAssistantRequest,
    complete_response,
    conversation_dict,
    fail_response,
    get_conversation,
    get_primary_conversation,
    list_conversations,
    prepare_request,
    recent_context_messages,
    search_messages,
)
from app.server.new_core.memory import (
    handle_explicit_command,
    schedule_extraction,
    select_for_prompt,
)
from app.server.new_core.models import IdeaUpload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


class AssistantMessageBody(BaseModel):
    text: str = Field(min_length=1, max_length=12_000)
    conversationId: str | None = Field(default=None, min_length=1, max_length=160)
    sessionId: str | None = Field(default=None, min_length=1, max_length=160)
    clientMessageId: str | None = Field(default=None, min_length=1, max_length=120)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    attachmentIds: list[str] = Field(default_factory=list, max_length=10)
    replyToMessageId: str | None = Field(default=None, min_length=1, max_length=32)


class AssistantConversationBody(BaseModel):
    title: str | None = Field(default=None, max_length=300)


_ASSISTANT_UPLOAD_ALLOWED = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/pdf",
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/zip",
    "application/x-zip-compressed",
}
_ASSISTANT_UPLOAD_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
    "text/plain": ".txt",
    "text/markdown": ".md",
    "text/csv": ".csv",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/zip": ".zip",
    "application/x-zip-compressed": ".zip",
}
_DOCUMENT_MAX_CHARS = 16_000


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
    event = {
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
    if body.clientMessageId:
        event["clientMessageId"] = body.clientMessageId
    return event


def _attach_conversation_context(
    event: dict[str, Any],
    history: PreparedAssistantRequest,
    db: Session,
) -> None:
    event["conversationHistory"] = recent_context_messages(
        db,
        user_id=history.conversation.userId,
        conversation_id=history.conversation.conversationId,
        exclude_message_id=history.user_message.messageId,
    )


def _extract_document_text(path: Path, mime_type: str) -> str | None:
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if mime_type in {"text/plain", "text/markdown", "text/csv"}:
        return raw.decode("utf-8", errors="replace")[:_DOCUMENT_MAX_CHARS].strip() or None
    if mime_type == "application/pdf":
        try:
            from pypdf import PdfReader

            text = "\n\n".join(
                str(page.extract_text() or "") for page in PdfReader(BytesIO(raw)).pages
            )
            return text[:_DOCUMENT_MAX_CHARS].strip() or None
        except Exception:  # noqa: BLE001 - a non-text PDF remains a safe attachment
            return None
    if mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        try:
            from xml.etree import ElementTree
            from zipfile import ZipFile

            with ZipFile(path) as archive:
                xml = archive.read("word/document.xml")
            root = ElementTree.fromstring(xml)
            paragraphs: list[str] = []
            for paragraph in root.iter(
                "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"
            ):
                parts = [
                    str(node.text or "")
                    for node in paragraph.iter(
                        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"
                    )
                ]
                if parts:
                    paragraphs.append("".join(parts))
            return "\n".join(paragraphs)[:_DOCUMENT_MAX_CHARS].strip() or None
        except Exception:  # noqa: BLE001 - malformed documents stay storage-only
            return None
    return None


def _attach_message_context(
    event: dict[str, Any],
    history: PreparedAssistantRequest,
    db: Session,
) -> None:
    uploads = db.scalars(
        select(IdeaUpload).where(
            IdeaUpload.assistantMessageId == history.user_message.messageId,
            IdeaUpload.userId == history.user_message.userId,
        )
    ).all()
    if uploads:
        by_id = {upload.uploadId: upload for upload in uploads}
        ordered = [by_id[upload_id] for upload_id in by_id]
        event["attachments"] = [
            {
                "uploadId": upload.uploadId,
                "fileName": upload.fileName,
                "mimeType": upload.mimeType,
                "sizeBytes": upload.sizeBytes,
            }
            for upload in ordered
        ]
        document_context: list[dict[str, str]] = []
        for upload in ordered:
            if upload.mimeType.startswith("image/"):
                continue
            text = _extract_document_text(Path(upload.storagePath), upload.mimeType)
            if text:
                document_context.append({"fileName": upload.fileName, "text": text})
        if document_context:
            event["documentContext"] = document_context
    if history.user_message.replyToMessageId and history.user_message.replyToText:
        event["replyTo"] = {
            "messageId": history.user_message.replyToMessageId,
            "text": history.user_message.replyToText,
        }


def _attach_memory(
    event: dict[str, Any],
    *,
    user_id: str,
    settings: Settings,
    db: Session,
) -> bool:
    """Inject long-term memories and apply explicit 记住/忘掉 (D024).

    Runs after the history transaction is committed so a memory failure can
    roll back safely without touching the user's message. Returns whether an
    explicit memory command was handled in this turn.
    """
    if not settings.memory_enabled:
        return False
    handled = False
    try:
        command = handle_explicit_command(db, user_id=user_id, text=str(event.get("text") or ""))
        lines = select_for_prompt(
            db,
            user_id=user_id,
            query_text=str(event.get("text") or ""),
            limit=settings.memory_inject_limit,
            max_chars=settings.memory_inject_max_chars,
        )
        db.commit()
    except Exception:  # noqa: BLE001 - memory must never block the assistant
        db.rollback()
        logger.warning("memory injection failed for user=%s", user_id, exc_info=True)
        return False
    event["memoryEnabled"] = True
    if lines:
        event["userMemory"] = lines
    if command is not None:
        event["memoryAction"] = command.summary
        handled = True
    return handled


def _memory_follow_up(
    *,
    user_id: str,
    user_text: str,
    settings: Settings,
    skip: bool,
) -> Callable[[str], None] | None:
    if skip or not settings.memory_enabled:
        return None

    def follow_up(response_text: str) -> None:
        try:
            schedule_extraction(
                user_id=user_id,
                user_text=user_text,
                assistant_text=response_text,
                settings=settings,
            )
        except Exception:  # noqa: BLE001
            logger.warning("memory extraction scheduling failed", exc_info=True)

    return follow_up


def _upload_mime(file: UploadFile) -> str:
    mime = (file.content_type or "").lower().strip()
    if mime in _ASSISTANT_UPLOAD_ALLOWED:
        return mime
    suffix = Path(file.filename or "").suffix.lower()
    by_suffix = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".pdf": "application/pdf",
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".csv": "text/csv",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".zip": "application/zip",
    }
    return by_suffix.get(suffix, mime)


@router.post("/attachments")
async def upload_assistant_attachments(
    files: list[UploadFile] = File(...),
    user_id: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    crud.cleanupExpiredIdeaMedia(db)
    if not files or len(files) > 10:
        raise HTTPException(status_code=400, detail="upload 1 to 10 files")
    results: list[dict[str, Any]] = []
    for file in files:
        mime = _upload_mime(file)
        if mime not in _ASSISTANT_UPLOAD_ALLOWED:
            raise HTTPException(
                status_code=415,
                detail="only images, PDF, TXT, Markdown, CSV, DOCX, and ZIP are supported",
            )
        content = await file.read(settings.idea_media_max_bytes + 1)
        if not content or len(content) > settings.idea_media_max_bytes:
            raise HTTPException(status_code=413, detail="attachment is empty or exceeds 20 MB")
        name = Path(file.filename or "attachment").name[:300]
        destination = settings.idea_media_path / f"{uuid4().hex}{_ASSISTANT_UPLOAD_EXT[mime]}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        try:
            row = crud.createIdeaUpload(
                db,
                userId=user_id,
                fileName=name,
                mimeType=mime,
                storagePath=str(destination),
                sizeBytes=len(content),
            )
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        results.append({key: row[key] for key in ("uploadId", "fileName", "mimeType", "sizeBytes")})
    return {"ok": True, "data": results}


@router.get("/attachments/{upload_id}")
def download_assistant_attachment(
    upload_id: str,
    user_id: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
) -> FileResponse:
    row = db.scalar(
        select(IdeaUpload).where(IdeaUpload.uploadId == upload_id, IdeaUpload.userId == user_id)
    )
    if row is None:
        raise HTTPException(status_code=404, detail="assistant attachment not found")
    path = Path(row.storagePath)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="assistant attachment file not found")
    disposition = "inline" if row.mimeType.startswith("image/") else "attachment"
    return FileResponse(
        path,
        media_type=row.mimeType or mimetypes.guess_type(row.fileName)[0],
        filename=row.fileName,
        content_disposition_type=disposition,
    )


@router.delete("/attachments/{upload_id}")
def delete_assistant_attachment(
    upload_id: str,
    user_id: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    row = db.scalar(
        select(IdeaUpload).where(IdeaUpload.uploadId == upload_id, IdeaUpload.userId == user_id)
    )
    if row is None:
        raise HTTPException(status_code=404, detail="assistant attachment not found")
    if row.assistantMessageId:
        raise HTTPException(
            status_code=409, detail="assistant attachment is already part of a message"
        )
    path = Path(row.storagePath)
    db.delete(row)
    db.commit()
    path.unlink(missing_ok=True)
    return {"ok": True, "data": {"uploadId": upload_id}}


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
            attachment_ids=body.attachmentIds,
            reply_to_message_id=body.replyToMessageId,
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
    on_complete: Callable[[str], None] | None = None,
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
                        chunk = str(payload["text"])
                        mode = str(payload.get("mode") or "").strip().lower()
                        # mode=new means a full snapshot of the current reply.
                        if mode in {"", "new"} or not response_parts:
                            response_parts[:] = [chunk]
                        else:
                            response_parts.append(chunk)
                    if event_type == "done":
                        response_text = (
                            str(payload.get("response") or "").strip()
                            or "".join(response_parts).strip()
                        )
                        complete_response(db, history, response_text)
                        completed = True
                        if on_complete is not None and history.assistant_message.stat == "complete":
                            on_complete(response_text)
                        # DSH's session id is intentionally different from
                        # the server-owned conversation id. Return both so
                        # the browser keeps reading the same conversation
                        # after the stream closes.
                        payload = {**payload, "conversationId": history.conversation.conversationId}
                    if event_type == "error" and not completed:
                        fail_response(
                            db,
                            history,
                            str(payload.get("message") or "助手暂时不可用，请稍后重试。"),
                        )
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
    _attach_conversation_context(event, history, db)
    _attach_message_context(event, history, db)
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
    memory_handled = _attach_memory(event, user_id=user_id, settings=settings, db=db)
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
    follow_up = _memory_follow_up(
        user_id=user_id, user_text=event["text"], settings=settings, skip=memory_handled
    )
    if follow_up is not None:
        follow_up(str(data["response"]))
    return {
        "ok": True,
        "data": {
            "sessionId": data.get("sessionId") or event["conversationId"],
            "conversationId": history.conversation.conversationId,
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
    _attach_conversation_context(event, history, db)
    _attach_message_context(event, history, db)
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
    memory_handled = _attach_memory(event, user_id=user_id, settings=settings, db=db)
    return StreamingResponse(
        _stream_dsh(
            event,
            endpoint=endpoint,
            token=token,
            history=history,
            db=db,
            on_complete=_memory_follow_up(
                user_id=user_id, user_text=event["text"], settings=settings, skip=memory_handled
            ),
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
