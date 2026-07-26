from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.server.auth.security import require_authenticated_user_id
from app.server.db.session import get_db
from app.server.feishu.bot_service import seal
from app.server.new_core.models import (
    FeishuBind,
    FeishuBot,
    FeishuChatPair,
    MsgLog,
    NotifyLog,
    nowIso,
)
from app.server.user_device.service import confirmFeishuChatPair, startFeishuChatPair

router = APIRouter(prefix="/api/feishu", tags=["feishu-pairing"])


def _local_time(value: str, timezone: ZoneInfo) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone)
    return parsed.astimezone(timezone)


def _usage_window(range_key: str, timezone: ZoneInfo) -> tuple[datetime, datetime]:
    end = datetime.now(timezone)
    days = {"today": 1, "7d": 7, "30d": 30}[range_key]
    start = end.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)
    return start, end


def _trend_rows(
    rows: list[MsgLog],
    *,
    start: datetime,
    end: datetime,
    timezone: ZoneInfo,
    range_key: str,
) -> list[dict[str, Any]]:
    step = timedelta(hours=1) if range_key == "today" else timedelta(days=1)
    bucket_start = start
    buckets: list[dict[str, Any]] = []
    while bucket_start <= end:
        buckets.append(
            {
                "startAt": bucket_start.isoformat(),
                "messages": 0,
                "forwarded": 0,
                "failed": 0,
            }
        )
        bucket_start += step
    for row in rows:
        observed = _local_time(row.createdAt, timezone)
        if observed is None:
            continue
        index = int((observed - start).total_seconds() // step.total_seconds())
        if index < 0 or index >= len(buckets):
            continue
        buckets[index]["messages"] += 1
        if row.stat == "forwarded":
            buckets[index]["forwarded"] += 1
        elif row.stat == "forward_failed":
            buckets[index]["failed"] += 1
    return buckets


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


@router.get("/usage")
def usage(
    range: Literal["today", "7d", "30d"] = "today",
    timezone_name: str = Query(default="Asia/Shanghai", alias="timezone", min_length=1, max_length=64),
    user_id: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(status_code=422, detail="timezone must be a valid IANA name") from exc
    start, end = _usage_window(range, timezone)
    messages = [
        row
        for row in db.scalars(
            select(MsgLog).where(MsgLog.userId == user_id, MsgLog.channel == "feishu")
        ).all()
        if (observed := _local_time(row.createdAt, timezone)) is not None and start <= observed <= end
    ]
    notifications = [
        row
        for row in db.scalars(
            select(NotifyLog).where(NotifyLog.userId == user_id, NotifyLog.channel == "feishu")
        ).all()
        if (observed := _local_time(row.scheduledAt, timezone)) is not None and start <= observed <= end
    ]
    intent_counts = Counter(row.intent or "unknown" for row in messages)
    forwarded = sum(row.stat == "forwarded" for row in messages)
    failed = sum(row.stat == "forward_failed" for row in messages)
    unsupported = sum(str(row.stat or "").startswith("unsupported:") for row in messages)
    recent = sorted(messages, key=lambda row: row.createdAt, reverse=True)[:8]
    return {
        "ok": True,
        "data": {
            "range": range,
            "timezone": timezone_name,
            "windowStart": start.isoformat(),
            "windowEnd": end.isoformat(),
            "totals": {
                "messages": len(messages),
                "forwarded": forwarded,
                "failed": failed,
                "unsupported": unsupported,
                "notificationsSent": sum(row.stat == "sent" for row in notifications),
                "notificationsFailed": sum(row.stat == "failed" for row in notifications),
            },
            "intents": [
                {"intent": intent, "count": count}
                for intent, count in sorted(intent_counts.items(), key=lambda item: (-item[1], item[0]))
            ],
            "trend": _trend_rows(
                messages,
                start=start,
                end=end,
                timezone=timezone,
                range_key=range,
            ),
            "recent": [
                {
                    "msgId": row.msgId,
                    "intent": row.intent,
                    "stat": row.stat,
                    "createdAt": row.createdAt,
                }
                for row in recent
            ],
        },
    }


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
