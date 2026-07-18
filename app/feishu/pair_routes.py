from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import require_authenticated_user_id
from app.db.session import get_db
from app.feishu.bot_service import seal
from app.new_core.models import FeishuBind, FeishuBot, FeishuChatPair, nowIso
from app.user_device.service import confirmFeishuChatPair, startFeishuChatPair

router = APIRouter(prefix="/api/feishu", tags=["feishu-pairing"])


def _default_bot(db: Session) -> FeishuBot:
    bot = db.scalar(
        select(FeishuBot)
        .where(FeishuBot.enabled.is_(True), FeishuBot.isDefault.is_(True))
        .order_by(FeishuBot.createdAt)
    )
    if bot is None:
        raise HTTPException(status_code=409, detail="no enabled default Feishu bot")
    return bot


def _pair_data(db: Session, pair: FeishuChatPair) -> dict[str, Any]:
    bot = db.get(FeishuBot, pair.botId)
    return {
        "pairId": pair.pairId,
        "botId": pair.botId,
        "botName": bot.botName if bot is not None else "SmartCore",
        "deviceName": bot.botName if bot is not None else "SmartCore",
        "deviceKind": "feishuBot",
        "claimCode": pair.claimCode,
        "stat": pair.stat,
        "expiresAt": pair.expiresAt,
    }


def _binding_data(db: Session, row: FeishuBind) -> dict[str, Any]:
    bot = db.get(FeishuBot, row.botId)
    return {
        "bindId": row.bindId,
        "botId": row.botId,
        "botName": bot.botName if bot is not None else "SmartCore",
        "chatType": row.chatType,
        "chatHint": f"…{row.chatId[-6:]}" if len(row.chatId) > 6 else "configured",
        "stat": row.stat,
        "isPrimary": row.isPrimary,
        "createdAt": row.createdAt,
        "lastSeenAt": row.lastSeenAt,
    }


@router.post("/pair/start")
def start_pair(
    user_id: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    pair = startFeishuChatPair(db, user_id, _default_bot(db).botId)
    return {"ok": True, "data": _pair_data(db, pair)}


@router.get("/pair/{pair_id}")
def read_pair(
    pair_id: str,
    user_id: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    pair = db.get(FeishuChatPair, pair_id)
    if pair is None or pair.userId != user_id:
        raise HTTPException(status_code=404, detail="Feishu pairing request not found")
    return {"ok": True, "data": _pair_data(db, pair)}


@router.post("/pair/{pair_id}/confirm")
def confirm_pair(
    pair_id: str,
    user_id: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    row = confirmFeishuChatPair(db, pair_id, user_id)
    pair = db.get(FeishuChatPair, pair_id)
    if pair is None:
        raise HTTPException(status_code=404, detail="Feishu pairing request not found")
    return {
        "ok": True,
        "data": {
            **_pair_data(db, pair),
            "bindId": row.bindId,
        },
    }


@router.get("/bindings")
def bindings(
    user_id: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    rows = db.scalars(
        select(FeishuBind)
        .where(FeishuBind.userId == user_id, FeishuBind.stat == "active")
        .order_by(FeishuBind.isPrimary.desc(), FeishuBind.createdAt)
    ).all()
    return {"ok": True, "data": [_binding_data(db, row) for row in rows]}


@router.delete("/bindings/{bind_id}")
def delete_binding(
    bind_id: str,
    user_id: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    row = db.get(FeishuBind, bind_id)
    if row is None or row.userId != user_id:
        raise HTTPException(status_code=404, detail="Feishu binding not found")
    was_primary = row.isPrimary
    db.delete(row)
    db.flush()
    if was_primary:
        replacement = db.scalar(
            select(FeishuBind)
            .where(FeishuBind.userId == user_id, FeishuBind.stat == "active")
            .order_by(FeishuBind.createdAt)
        )
        if replacement is not None:
            replacement.isPrimary = True
            replacement.updatedAt = nowIso()
    for bot in db.scalars(select(FeishuBot).where(FeishuBot.userId == user_id)).all():
        primary = db.scalar(
            select(FeishuBind).where(
                FeishuBind.userId == user_id,
                FeishuBind.botId == bot.botId,
                FeishuBind.stat == "active",
                FeishuBind.isPrimary.is_(True),
            )
        )
        bot.defaultChatCipher = seal(primary.chatId) if primary is not None else None
        bot.updatedAt = nowIso()
    db.commit()
    return {"ok": True, "data": {"bindId": bind_id, "deleted": True}}
