from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import (
    create_session_token,
    require_authenticated_actor_id,
    require_authenticated_user_id,
)
from app.config import get_settings
from app.db.session import get_db
from app.feishu.bot_service import botDict, open_sealed, seal
from app.feishu.client import FeishuAPIError, FeishuClient
from app.new_core.models import ActLog, AppUser, FeishuBind, FeishuBot, nowIso
from app.user_device.service import confirmFeishuChatPair, startFeishuChatPair

router = APIRouter(prefix="/api/admin", tags=["admin"])


class ActiveUserBody(BaseModel):
    userId: str


class FeishuBotBody(BaseModel):
    botName: str = Field(min_length=1, max_length=100)
    appId: str = Field(min_length=3, max_length=200)
    appSecret: str = Field(min_length=3, max_length=500)
    verificationToken: str = Field(min_length=3, max_length=500)
    encryptKey: str = Field(min_length=3, max_length=500)
    defaultChatId: str | None = Field(default=None, max_length=300)
    isDefault: bool = False


class FeishuBotUpdateBody(BaseModel):
    botName: str | None = Field(default=None, min_length=1, max_length=100)
    appId: str | None = Field(default=None, min_length=3, max_length=200)
    appSecret: str | None = Field(default=None, min_length=3, max_length=500)
    verificationToken: str | None = Field(default=None, min_length=3, max_length=500)
    encryptKey: str | None = Field(default=None, min_length=3, max_length=500)
    defaultChatId: str | None = Field(default=None, max_length=300)
    isDefault: bool | None = None


def _public(user: AppUser) -> dict[str, Any]:
    return {"userId": user.userId, "loginName": user.loginName, "displayName": user.displayName, "role": user.role, "stat": user.stat}


def _actor(db: Session, userId: str) -> AppUser:
    user = db.get(AppUser, userId)
    if user is None or user.stat != "active":
        raise HTTPException(status_code=401, detail="session user is unavailable")
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="administrator role required")
    return user


def _bot(db: Session, botId: str, activeUserId: str) -> FeishuBot:
    bot = db.get(FeishuBot, botId)
    if bot is None or bot.userId != activeUserId:
        raise HTTPException(status_code=404, detail="Feishu bot not found")
    return bot


def _set_default(db: Session, bot: FeishuBot) -> None:
    if not bot.isDefault:
        return
    for row in db.scalars(select(FeishuBot).where(FeishuBot.userId == bot.userId, FeishuBot.botId != bot.botId)):
        row.isDefault = False


@router.get("/users")
def users(userId: str = Depends(require_authenticated_actor_id), db: Session = Depends(get_db)) -> dict[str, Any]:
    _actor(db, userId)
    return {"ok": True, "data": [_public(row) for row in db.scalars(select(AppUser).where(AppUser.stat == "active").order_by(AppUser.createdAt))]}


@router.post("/activeUser")
def activeUser(body: ActiveUserBody, response: Response, userId: str = Depends(require_authenticated_actor_id), db: Session = Depends(get_db)) -> dict[str, Any]:
    actor = _actor(db, userId)
    selected = db.get(AppUser, body.userId)
    if selected is None or selected.stat != "active":
        raise HTTPException(status_code=404, detail="target user not found")
    db.add(ActLog(userId=selected.userId, actorKind="user", actorId=actor.userId, action="update", targetKind="user", targetId=selected.userId))
    db.commit()
    settings = get_settings()
    response.set_cookie(key=settings.auth_cookie_name, value=create_session_token(selected.userId, actor_user_id=actor.userId), max_age=settings.auth_session_hours * 3600, httponly=True, secure=settings.auth_cookie_secure, samesite="lax", path="/")
    return {"ok": True, "data": {"actorUserId": actor.userId, "activeUser": _public(selected), "switchedAt": nowIso()}}


@router.get("/feishuBots")
def feishuBots(
    actorId: str = Depends(require_authenticated_actor_id),
    activeUserId: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _actor(db, actorId)
    rows = db.scalars(select(FeishuBot).where(FeishuBot.userId == activeUserId).order_by(FeishuBot.createdAt)).all()
    return {"ok": True, "data": [botDict(row) for row in rows]}


@router.post("/feishuBots")
def createFeishuBot(
    body: FeishuBotBody,
    actorId: str = Depends(require_authenticated_actor_id),
    activeUserId: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _actor(db, actorId)
    if db.scalar(select(FeishuBot.botId).where(FeishuBot.userId == activeUserId)) is not None:
        raise HTTPException(status_code=409, detail="each SmartCore user can configure one Feishu bot")
    bot = FeishuBot(
        userId=activeUserId,
        botName=body.botName.strip(),
        appId=body.appId.strip(),
        appSecretCipher=seal(body.appSecret.strip()),
        verificationTokenCipher=seal(body.verificationToken.strip()),
        encryptKeyCipher=seal(body.encryptKey.strip()),
        defaultChatCipher=seal(body.defaultChatId.strip()) if body.defaultChatId and body.defaultChatId.strip() else None,
        enabled=True,
        isDefault=body.isDefault,
    )
    db.add(bot)
    db.flush()
    _set_default(db, bot)
    db.commit()
    db.refresh(bot)
    return {"ok": True, "data": botDict(bot)}


@router.patch("/feishuBots/{botId}")
def updateFeishuBot(
    botId: str,
    body: FeishuBotUpdateBody,
    actorId: str = Depends(require_authenticated_actor_id),
    activeUserId: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _actor(db, actorId)
    bot = _bot(db, botId, activeUserId)
    if body.botName is not None:
        bot.botName = body.botName.strip()
    if body.appId is not None:
        bot.appId = body.appId.strip()
    if body.appSecret is not None:
        bot.appSecretCipher = seal(body.appSecret.strip())
    if body.verificationToken is not None:
        bot.verificationTokenCipher = seal(body.verificationToken.strip())
    if body.encryptKey is not None:
        bot.encryptKeyCipher = seal(body.encryptKey.strip())
    if body.defaultChatId is not None:
        bot.defaultChatCipher = seal(body.defaultChatId.strip()) if body.defaultChatId.strip() else None
    if body.isDefault is not None:
        bot.isDefault = body.isDefault
    bot.updatedAt = nowIso()
    _set_default(db, bot)
    db.commit()
    return {"ok": True, "data": botDict(bot)}


@router.post("/feishuBots/{botId}/toggle")
def toggleFeishuBot(
    botId: str,
    actorId: str = Depends(require_authenticated_actor_id),
    activeUserId: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _actor(db, actorId)
    bot = _bot(db, botId, activeUserId)
    bot.enabled = not bot.enabled
    bot.updatedAt = nowIso()
    db.commit()
    return {"ok": True, "data": botDict(bot)}


@router.post("/feishuBots/{botId}/pair/start")
def startFeishuBotPair(
    botId: str,
    actorId: str = Depends(require_authenticated_actor_id),
    activeUserId: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _actor(db, actorId)
    bot = _bot(db, botId, activeUserId)
    if not bot.enabled:
        raise HTTPException(status_code=409, detail="enable the Feishu bot before pairing")
    pair = startFeishuChatPair(db, activeUserId, bot.botId)
    return {"ok": True, "data": {"pairId": pair.pairId, "claimCode": pair.claimCode, "expiresAt": pair.expiresAt, "stat": pair.stat, "botId": bot.botId}}


@router.post("/feishuBots/{botId}/pair/{pairId}/confirm")
def confirmFeishuBotChatPair(
    botId: str,
    pairId: str,
    actorId: str = Depends(require_authenticated_actor_id),
    activeUserId: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _actor(db, actorId)
    _bot(db, botId, activeUserId)
    row = confirmFeishuChatPair(db, pairId, activeUserId)
    return {"ok": True, "data": {"bindId": row.bindId, "chatId": row.chatId, "stat": row.stat, "isPrimary": row.isPrimary}}


def _bind_dict(row: FeishuBind) -> dict[str, Any]:
    return {"bindId": row.bindId, "chatId": row.chatId, "chatType": row.chatType, "stat": row.stat, "isPrimary": row.isPrimary, "createdAt": row.createdAt, "lastSeenAt": row.lastSeenAt}


@router.get("/feishuBots/{botId}/binds")
def feishuBinds(botId: str, actorId: str = Depends(require_authenticated_actor_id), activeUserId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db)) -> dict[str, Any]:
    _actor(db, actorId)
    _bot(db, botId, activeUserId)
    rows = db.scalars(select(FeishuBind).where(FeishuBind.botId == botId).order_by(FeishuBind.isPrimary.desc(), FeishuBind.createdAt)).all()
    return {"ok": True, "data": [_bind_dict(row) for row in rows]}


@router.post("/feishuBots/{botId}/binds/{bindId}/primary")
def setPrimaryFeishuBind(botId: str, bindId: str, actorId: str = Depends(require_authenticated_actor_id), activeUserId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db)) -> dict[str, Any]:
    _actor(db, actorId)
    bot = _bot(db, botId, activeUserId)
    selected = db.get(FeishuBind, bindId)
    if selected is None or selected.botId != botId or selected.userId != activeUserId or selected.stat != "active":
        raise HTTPException(status_code=404, detail="Feishu chat binding not found")
    for row in db.scalars(select(FeishuBind).where(FeishuBind.botId == botId)):
        row.isPrimary = row.bindId == bindId
        row.updatedAt = nowIso()
    bot.defaultChatCipher = seal(selected.chatId)
    bot.updatedAt = nowIso()
    db.commit()
    return {"ok": True, "data": _bind_dict(selected)}


@router.delete("/feishuBots/{botId}/binds/{bindId}")
def deleteFeishuBind(botId: str, bindId: str, actorId: str = Depends(require_authenticated_actor_id), activeUserId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db)) -> dict[str, Any]:
    _actor(db, actorId)
    bot = _bot(db, botId, activeUserId)
    selected = db.get(FeishuBind, bindId)
    if selected is None or selected.botId != botId or selected.userId != activeUserId:
        raise HTTPException(status_code=404, detail="Feishu chat binding not found")
    was_primary = selected.isPrimary
    db.delete(selected)
    db.flush()
    if was_primary:
        replacement = db.scalar(select(FeishuBind).where(FeishuBind.botId == botId, FeishuBind.stat == "active").order_by(FeishuBind.createdAt))
        if replacement is None:
            bot.defaultChatCipher = None
        else:
            replacement.isPrimary = True
            replacement.updatedAt = nowIso()
            bot.defaultChatCipher = seal(replacement.chatId)
        bot.updatedAt = nowIso()
    db.commit()
    return {"ok": True, "data": {"bindId": bindId, "deleted": True}}


@router.post("/feishuBots/{botId}/test")
def testFeishuBot(
    botId: str,
    actorId: str = Depends(require_authenticated_actor_id),
    activeUserId: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _actor(db, actorId)
    bot = _bot(db, botId, activeUserId)
    binding = db.scalar(select(FeishuBind).where(FeishuBind.botId == bot.botId, FeishuBind.stat == "active", FeishuBind.isPrimary.is_(True)))
    target = binding.chatId if binding is not None else ""
    if not target:
        raise HTTPException(status_code=409, detail="pair a Feishu account before sending a test message")
    try:
        FeishuClient(bot.appId, open_sealed(bot.appSecretCipher)).send_text(target, "SmartCore 飞书机器人连接测试成功。")
    except FeishuAPIError as exc:
        bot.lastTestAt = nowIso()
        bot.lastTestStat = "failed"
        bot.lastTestMessage = str(exc)[:300]
        db.commit()
        raise HTTPException(status_code=502, detail="Feishu test message failed") from exc
    bot.lastTestAt = nowIso()
    bot.lastTestStat = "sent"
    bot.lastTestMessage = "test message sent"
    db.commit()
    return {"ok": True, "data": botDict(bot)}


@router.delete("/feishuBots/{botId}")
def deleteFeishuBot(
    botId: str,
    actorId: str = Depends(require_authenticated_actor_id),
    activeUserId: str = Depends(__import__("app.auth.security", fromlist=["require_authenticated_user_id"]).require_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _actor(db, actorId)
    bot = _bot(db, botId, activeUserId)
    if bot.deviceId:
        from app.user_device.service import removeDevice
        removeDevice(db, activeUserId, bot.deviceId)
        bot = db.get(FeishuBot, botId)
        if bot is None:
            return {"ok": True, "data": {"botId": botId, "deleted": True}}
    db.delete(bot)
    db.commit()
    return {"ok": True, "data": {"botId": botId, "deleted": True}}
