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
from app.server.new_core.daily_work_context import build_daily_work_context
from app.server.new_core.models import AppUser

PostEvent = Callable[[dict[str, Any]], None]


def _has_daily_work_evidence(context: dict[str, Any]) -> bool:
    if any(context.get(key) for key in ("codexReports", "computerWorkBlocks", "plans")):
        return True
    totals = context.get("totals")
    return isinstance(totals, dict) and int(totals.get("activeSeconds") or 0) > 0


def _post_assistant_event(settings: Settings, event: dict[str, Any]) -> None:
    endpoint = settings.assistant_events_endpoint.strip()
    if not endpoint:
        raise RuntimeError("Assistant events endpoint is not configured")
    headers = {"Content-Type": "application/json"}
    if settings.assistant_events_token:
        headers["Authorization"] = f"Bearer {settings.assistant_events_token}"
    response = httpx.post(endpoint, json=event, headers=headers, timeout=15)
    response.raise_for_status()


def _active_users(db: Session) -> list[AppUser]:
    return list(
        db.scalars(select(AppUser).where(AppUser.stat == "active").order_by(AppUser.createdAt))
    )


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
    deliver = post_event or (lambda event: _post_assistant_event(settings, event))
    result = {"queued": 0, "skipped": 0, "failed": 0}

    for user in _active_users(db):
        context = build_daily_work_context(
            db,
            user_id=user.userId,
            report_date=report_date,
            timezone_name=settings.daily_summary_timezone,
        )
        if not _has_daily_work_evidence(context):
            result["skipped"] += 1
            continue
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
            "user": {
                "user_id": user.userId,
                "display_name": user.displayName,
                "language": user.language,
            },
            "agentScope": scope,
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
