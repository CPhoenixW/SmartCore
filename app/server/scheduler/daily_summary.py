from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.server.agent.scope import issue_agent_scope
from app.server.config import Settings
from app.server.new_core.daily_summary_service import (
    queue_daily_summary,
    store_daily_summary,
)
from app.server.new_core.models import AppUser, FeishuBind, FeishuBot

PostEvent = Callable[[dict[str, Any]], None]


def _post_openclaw_event(settings: Settings, event: dict[str, Any]) -> None:
    endpoint = settings.openclaw_events_endpoint.strip()
    if not endpoint:
        raise RuntimeError("OpenClaw events endpoint is not configured")
    headers = {"Content-Type": "application/json"}
    if settings.openclaw_events_token:
        headers["Authorization"] = f"Bearer {settings.openclaw_events_token}"
    response = httpx.post(endpoint, json=event, headers=headers, timeout=15)
    response.raise_for_status()


def _primary_bindings(db: Session) -> list[tuple[AppUser, FeishuBind, FeishuBot]]:
    rows = db.execute(
        select(AppUser, FeishuBind, FeishuBot)
        .join(FeishuBind, FeishuBind.userId == AppUser.userId)
        .join(FeishuBot, FeishuBot.botId == FeishuBind.botId)
        .where(
            AppUser.stat == "active",
            FeishuBind.stat == "active",
            FeishuBind.isPrimary.is_(True),
            FeishuBot.enabled.is_(True),
        )
        .order_by(AppUser.createdAt, FeishuBind.updatedAt.desc())
    ).all()
    selected: dict[str, tuple[AppUser, FeishuBind, FeishuBot]] = {}
    for user, binding, bot in rows:
        selected.setdefault(user.userId, (user, binding, bot))
    return list(selected.values())


def dispatch_daily_summaries(
    db: Session,
    *,
    settings: Settings,
    now: datetime,
    post_event: PostEvent | None = None,
) -> dict[str, int]:
    timezone = ZoneInfo(settings.daily_summary_timezone)
    local_now = now.astimezone(timezone)
    report_date = local_now.date().isoformat()
    deliver = post_event or (lambda event: _post_openclaw_event(settings, event))
    result = {"queued": 0, "skipped": 0, "failed": 0}

    for user, binding, bot in _primary_bindings(db):
        _row, should_dispatch = queue_daily_summary(
            db,
            user_id=user.userId,
            report_date=report_date,
        )
        if not should_dispatch:
            result["skipped"] += 1
            continue
        event_id = f"daily-summary:{user.userId}:{report_date}"
        scope = issue_agent_scope(
            userId=user.userId,
            purpose="daily_summary",
            reportDate=report_date,
            ttl_seconds=1800,
        )
        delivery_scope = issue_agent_scope(
            userId=user.userId,
            botId=bot.botId,
            chatId=binding.chatId,
            purpose="feishu",
            ttl_seconds=1800,
        )
        event = {
            "event_id": event_id,
            "source": "smartcore-scheduler",
            "event_type": "daily_summary",
            "reportDate": report_date,
            "text": (
                f"生成 {report_date} 的每日总结。按项目汇总 Codex 当日成果、电脑活跃投入和 Plan "
                "description 中的人工结果。"
            ),
            "userId": user.userId,
            "sourceBindId": binding.bindId,
            "chat_id": binding.chatId,
            "chat": {"chat_id": binding.chatId, "chat_type": binding.chatType},
            "user": {
                "user_id": user.userId,
                "display_name": user.displayName,
                "language": user.language,
            },
            "agentScope": scope,
            "deliveryScope": delivery_scope,
            "request": {
                "timezone": settings.daily_summary_timezone,
                "now": local_now.replace(microsecond=0).isoformat(),
                "outputLanguage": "zh-CN",
            },
        }
        try:
            deliver(event)
            result["queued"] += 1
        except Exception as exc:
            store_daily_summary(
                db,
                user_id=user.userId,
                report_date=report_date,
                stat="failed",
                error_message=f"adapter dispatch failed: {type(exc).__name__}",
            )
            result["failed"] += 1
    return result
