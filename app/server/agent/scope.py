from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass

from fastapi import Header, HTTPException

from app.server.auth.security import _b64decode, _b64encode, auth_secret

SCOPE_HEADER = "X-SmartCore-Agent-Scope"


@dataclass(frozen=True)
class AgentScope:
    userId: str
    purpose: str
    botId: str | None = None
    chatId: str | None = None


def issue_ocr_evidence(*, userId: str, uploadId: str, ttl_seconds: int = 600) -> str:
    """Issue short-lived proof that an owned upload completed OCR."""
    if not userId or not uploadId:
        raise ValueError("invalid OCR evidence fields")
    payload = {
        "v": 1,
        "purpose": "idea-image-ocr",
        "userId": userId,
        "uploadId": uploadId,
        "exp": int(time.time()) + ttl_seconds,
    }
    encoded = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _b64encode(
        hmac.new(auth_secret(), encoded.encode("ascii"), hashlib.sha256).digest()
    )
    return f"{encoded}.{signature}"


def verify_ocr_evidence(token: str, *, userId: str, uploadId: str) -> bool:
    """Validate owner/upload-bound OCR proof without exposing its contents."""
    try:
        encoded, signature = token.split(".", 1)
        expected = _b64encode(
            hmac.new(auth_secret(), encoded.encode("ascii"), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(signature, expected):
            return False
        payload = json.loads(_b64decode(encoded))
        return bool(
            payload.get("v") == 1
            and payload.get("purpose") == "idea-image-ocr"
            and payload.get("userId") == userId
            and payload.get("uploadId") == uploadId
            and int(payload.get("exp", 0)) >= int(time.time())
        )
    except (ValueError, TypeError, json.JSONDecodeError):
        return False


def issue_agent_scope(
    *,
    userId: str,
    botId: str | None = None,
    chatId: str = "",
    purpose: str = "feishu",
    ttl_seconds: int = 600,
) -> str:
    if purpose not in {"feishu", "web"}:
        raise ValueError("unsupported agent scope purpose")
    if not userId or (purpose == "feishu" and (not botId or not chatId)):
        raise ValueError("invalid agent scope routing")
    payload = {
        "v": 1,
        "purpose": purpose,
        "userId": userId,
        "botId": botId,
        "chatId": chatId,
        "exp": int(time.time()) + ttl_seconds,
    }
    encoded = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _b64encode(hmac.new(auth_secret(), encoded.encode("ascii"), hashlib.sha256).digest())
    return f"{encoded}.{signature}"


def require_agent_scope(
    x_smartcore_agent_scope: str | None = Header(default=None, alias=SCOPE_HEADER),
) -> AgentScope:
    if not x_smartcore_agent_scope:
        raise HTTPException(status_code=401, detail="missing agent scope")
    try:
        encoded, signature = x_smartcore_agent_scope.split(".", 1)
        expected = _b64encode(hmac.new(auth_secret(), encoded.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError("signature")
        payload = json.loads(_b64decode(encoded))
        purpose = str(payload.get("purpose") or "")
        if payload.get("v") != 1 or purpose not in {"feishu", "web"} or int(payload.get("exp", 0)) < int(time.time()):
            raise ValueError("expired")
        user_id = str(payload.get("userId") or "").strip()
        bot_id = str(payload.get("botId") or "").strip()
        chat_id = str(payload.get("chatId") or "").strip()
        if not user_id or (purpose == "feishu" and (not bot_id or not chat_id)):
            raise ValueError("fields")
        return AgentScope(userId=user_id, purpose=purpose, botId=bot_id or None, chatId=chat_id or None)
    except (ValueError, TypeError, json.JSONDecodeError):
        raise HTTPException(status_code=401, detail="invalid agent scope") from None
