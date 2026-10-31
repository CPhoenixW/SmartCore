from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.server.new_core.models import AssistantConversation, AssistantMessage, nowIso

MAX_CONVERSATION_ID = 160
MAX_CLIENT_MESSAGE_ID = 120
MAX_MESSAGE_TEXT = 12_000
MAX_SEARCH_QUERY = 120


def new_conversation_id() -> str:
    return f"pwa-{uuid.uuid4().hex}"


def primary_conversation_id(user_id: str) -> str:
    """Return the opaque, stable conversation id shared by every device.

    The id is derived from the verified owner only so a fresh browser cannot
    accidentally create a second chat. Existing conversations are migrated to
    the newest active row by :func:`get_primary_conversation`.
    """
    digest = hashlib.sha256(f"smartcore-primary:{user_id}".encode()).hexdigest()
    return f"pwa-primary-{digest[:32]}"


def _title_from_text(text: str) -> str:
    compact = re.sub(r"\s+", " ", text.strip())
    return compact[:60] or "新会话"


def _conversation_id(value: str | None) -> str:
    value = str(value or "").strip()
    if not value:
        return new_conversation_id()
    if len(value) > MAX_CONVERSATION_ID:
        raise ValueError("conversationId is too long")
    return value


def ensure_conversation(
    db: Session,
    *,
    user_id: str,
    conversation_id: str | None = None,
    title: str | None = None,
) -> AssistantConversation:
    resolved_id = _conversation_id(conversation_id)
    row = db.get(AssistantConversation, resolved_id)
    if row is not None:
        if row.userId != user_id:
            raise ValueError("conversation not found")
        if row.stat == "archived":
            row.stat = "active"
            row.updatedAt = nowIso()
        if title and row.title == "新会话":
            row.title = _title_from_text(title)
        return row
    row = AssistantConversation(
        conversationId=resolved_id,
        userId=user_id,
        title=_title_from_text(title or ""),
        createdAt=nowIso(),
        updatedAt=nowIso(),
    )
    db.add(row)
    db.flush()
    return row


def get_primary_conversation(db: Session, *, user_id: str) -> AssistantConversation:
    """Return the single active conversation for an owner.

    Older releases allowed multiple active conversations. Keep their rows for
    audit/history, but archive all except the most recently updated one when
    the owner first uses the single-chat UI. A new owner receives a stable id,
    which makes the same server conversation appear on every device.
    """
    rows = db.scalars(
        select(AssistantConversation)
        .where(
            AssistantConversation.userId == user_id,
            AssistantConversation.stat == "active",
        )
        .order_by(AssistantConversation.updatedAt.desc(), AssistantConversation.createdAt.desc())
    ).all()
    if rows:
        primary = rows[0]
        if len(rows) > 1:
            timestamp = nowIso()
            for duplicate in rows[1:]:
                duplicate.stat = "archived"
                duplicate.updatedAt = timestamp
        return primary
    return ensure_conversation(
        db,
        user_id=user_id,
        conversation_id=primary_conversation_id(user_id),
        title="SmartCore 助手",
    )


def _assistant_client_id(client_message_id: str | None) -> str | None:
    value = str(client_message_id or "").strip()
    if not value:
        return None
    if len(value) > MAX_CLIENT_MESSAGE_ID:
        raise ValueError("clientMessageId is too long")
    return value


@dataclass
class PreparedAssistantRequest:
    conversation: AssistantConversation
    user_message: AssistantMessage
    assistant_message: AssistantMessage
    replay_response: str | None = None


def prepare_request(
    db: Session,
    *,
    user_id: str,
    conversation_id: str | None,
    text: str,
    client_message_id: str | None,
) -> PreparedAssistantRequest:
    text = text.strip()
    if not text:
        raise ValueError("assistant message cannot be empty")
    if len(text) > MAX_MESSAGE_TEXT:
        raise ValueError("assistant message is too long")
    client_id = _assistant_client_id(client_message_id)
    # The web assistant is intentionally one continuous conversation. Ignore
    # stale ids sent by older clients and always resolve the server-owned
    # primary row so multiple devices converge on the same history.
    conversation = get_primary_conversation(db, user_id=user_id)
    user_message = None
    if client_id:
        user_message = db.scalar(
            select(AssistantMessage).where(
                AssistantMessage.userId == user_id,
                AssistantMessage.clientMessageId == client_id,
                AssistantMessage.role == "user",
            )
        )
        if user_message is not None and user_message.conversationId != conversation.conversationId:
            raise ValueError("clientMessageId is already used by another conversation")
    if user_message is None:
        user_message = AssistantMessage(
            conversationId=conversation.conversationId,
            userId=user_id,
            role="user",
            text=text,
            clientMessageId=client_id,
            stat="complete",
        )
        db.add(user_message)
        db.flush()
        if conversation.title == "新会话":
            conversation.title = _title_from_text(text)

    assistant_client_id = f"{client_id}:assistant" if client_id else None
    assistant_message = None
    if assistant_client_id:
        assistant_message = db.scalar(
            select(AssistantMessage).where(
                AssistantMessage.userId == user_id,
                AssistantMessage.clientMessageId == assistant_client_id,
                AssistantMessage.role == "assistant",
            )
        )
    if assistant_message is None:
        assistant_message = AssistantMessage(
            conversationId=conversation.conversationId,
            userId=user_id,
            role="assistant",
            text="",
            clientMessageId=assistant_client_id,
            stat="pending",
        )
        db.add(assistant_message)
        db.flush()
    elif assistant_message.stat == "complete":
        return PreparedAssistantRequest(
            conversation=conversation,
            user_message=user_message,
            assistant_message=assistant_message,
            replay_response=assistant_message.text,
        )
    else:
        assistant_message.text = ""
        assistant_message.stat = "pending"
    conversation.updatedAt = nowIso()
    conversation.lastMessageAt = nowIso()
    return PreparedAssistantRequest(
        conversation=conversation,
        user_message=user_message,
        assistant_message=assistant_message,
    )


def complete_response(db: Session, request: PreparedAssistantRequest, text: str) -> None:
    response = text.strip()
    if not response:
        fail_response(db, request, "助手没有返回可显示的答案。")
        return
    request.assistant_message.text = response[:MAX_MESSAGE_TEXT]
    request.assistant_message.stat = "complete"
    request.conversation.updatedAt = nowIso()
    request.conversation.lastMessageAt = nowIso()
    db.commit()


def fail_response(db: Session, request: PreparedAssistantRequest, message: str) -> None:
    request.assistant_message.text = message[:MAX_MESSAGE_TEXT]
    request.assistant_message.stat = "failed"
    request.conversation.updatedAt = nowIso()
    request.conversation.lastMessageAt = nowIso()
    db.commit()


def conversation_dict(row: AssistantConversation) -> dict[str, Any]:
    return {
        "conversationId": row.conversationId,
        "title": row.title,
        "stat": row.stat,
        "createdAt": row.createdAt,
        "updatedAt": row.updatedAt,
        "lastMessageAt": row.lastMessageAt,
    }


def message_dict(row: AssistantMessage) -> dict[str, Any]:
    return {
        "messageId": row.messageId,
        "conversationId": row.conversationId,
        "role": row.role,
        "text": row.text,
        "stat": row.stat,
        "createdAt": row.createdAt,
    }


def list_conversations(db: Session, *, user_id: str, limit: int = 30) -> list[dict[str, Any]]:
    del limit  # Kept in the API contract for older clients; there is one chat now.
    return [conversation_dict(get_primary_conversation(db, user_id=user_id))]


def get_conversation(
    db: Session,
    *,
    user_id: str,
    conversation_id: str,
    message_limit: int = 500,
) -> dict[str, Any] | None:
    row = db.get(AssistantConversation, conversation_id)
    if row is None or row.userId != user_id:
        return None
    messages = db.scalars(
        select(AssistantMessage)
        .where(
            AssistantMessage.conversationId == conversation_id,
            AssistantMessage.userId == user_id,
            AssistantMessage.stat != "pending",
        )
        .order_by(AssistantMessage.createdAt.asc())
        .limit(max(1, min(message_limit, 1000)))
    ).all()
    return {
        **conversation_dict(row),
        "messages": [message_dict(message) for message in messages],
    }


def recent_context_messages(
    db: Session,
    *,
    user_id: str,
    conversation_id: str,
    exclude_message_id: str | None = None,
    limit: int = 8,
    max_chars: int = 6000,
) -> list[dict[str, str]]:
    """Return a small, owner-scoped context window for a fresh DSH turn.

    The PWA keeps one server conversation, while each DSH request gets a fresh
    model session. Keeping the context window here prevents an old model
    session's tool schemas and reasoning traces from growing without bound.
    """
    conditions = [
        AssistantMessage.userId == user_id,
        AssistantMessage.conversationId == conversation_id,
        AssistantMessage.stat == "complete",
    ]
    if exclude_message_id:
        conditions.append(AssistantMessage.messageId != exclude_message_id)
    rows = db.scalars(
        select(AssistantMessage)
        .where(*conditions)
        .order_by(AssistantMessage.createdAt.desc(), AssistantMessage.messageId.desc())
        .limit(max(1, min(limit, 20)))
    ).all()

    result: list[dict[str, str]] = []
    used = 0
    for row in reversed(rows):
        text = row.text.strip()
        if not text:
            continue
        remaining = max_chars - used
        if remaining <= 0:
            break
        text = text[: min(1800, remaining)]
        result.append({"role": row.role, "text": text})
        used += len(text)
    return result


def search_messages(
    db: Session,
    *,
    user_id: str,
    query: str,
    limit: int = 30,
    conversation_id: str | None = None,
) -> list[dict[str, Any]]:
    compact = re.sub(r"\s+", " ", str(query or "").strip())
    if not compact:
        return []
    if len(compact) > MAX_SEARCH_QUERY:
        raise ValueError("search query is too long")
    terms = [part for part in compact.split(" ") if part]
    conditions = []
    for term in terms:
        pattern = f"%{term}%"
        conditions.append(
            or_(
                AssistantMessage.text.ilike(pattern),
                AssistantConversation.title.ilike(pattern),
            )
        )
    where_conditions = [
        AssistantMessage.userId == user_id,
        AssistantConversation.userId == user_id,
        AssistantMessage.stat == "complete",
        and_(*conditions),
    ]
    if conversation_id:
        where_conditions.append(AssistantMessage.conversationId == conversation_id)
    rows = db.execute(
        select(AssistantMessage, AssistantConversation)
        .join(
            AssistantConversation,
            AssistantConversation.conversationId == AssistantMessage.conversationId,
        )
        .where(*where_conditions)
        .order_by(AssistantMessage.createdAt.desc())
        .limit(max(1, min(limit, 100)))
    ).all()
    result = []
    for message, conversation in rows:
        text = message.text
        result.append(
            {
                "conversationId": conversation.conversationId,
                "title": conversation.title,
                "messageId": message.messageId,
                "role": message.role,
                "text": text,
                "snippet": text[:180],
                "createdAt": message.createdAt,
            }
        )
    return result


def archive_conversation(db: Session, *, user_id: str, conversation_id: str) -> bool:
    row = db.get(AssistantConversation, conversation_id)
    if row is None or row.userId != user_id:
        return False
    row.stat = "archived"
    row.updatedAt = nowIso()
    db.commit()
    return True


