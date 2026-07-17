from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass

from fastapi import Header, HTTPException

from app.auth.security import _b64decode, _b64encode, auth_secret

SCOPE_HEADER = "X-SmartCore-Agent-Scope"


@dataclass(frozen=True)
class AgentScope:
    userId: str
    botId: str
    chatId: str


def issue_agent_scope(*, userId: str, botId: str | None, chatId: str, ttl_seconds: int = 600) -> str:
    if not userId or not botId or not chatId:
        raise ValueError("Feishu scope requires user, bot, and chat")
    payload = {
        "v": 1,
        "purpose": "feishu",
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
        if payload.get("v") != 1 or payload.get("purpose") != "feishu" or int(payload.get("exp", 0)) < int(time.time()):
            raise ValueError("expired")
        user_id = str(payload.get("userId") or "").strip()
        bot_id = str(payload.get("botId") or "").strip()
        chat_id = str(payload.get("chatId") or "").strip()
        if not user_id or not bot_id or not chat_id:
            raise ValueError("fields")
        return AgentScope(userId=user_id, botId=bot_id, chatId=chat_id)
    except (ValueError, TypeError, json.JSONDecodeError):
        raise HTTPException(status_code=401, detail="invalid agent scope") from None
