from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.server.agent.scope import issue_agent_scope
from app.server.computer.insights import queue_daily_log, queue_hourly_analysis
from app.server.config import Settings
from app.server.new_core.models import LifeDevice, nowIso

PostEvent = Callable[[dict[str, Any]], None]


def _post(settings: Settings, event: dict[str, Any]) -> None:
    endpoint = settings.openclaw_events_endpoint.strip()
    if not endpoint:
        raise RuntimeError("OpenClaw events endpoint is not configured")
    headers = {"Content-Type": "application/json"}
    if settings.openclaw_events_token:
        headers["Authorization"] = f"Bearer {settings.openclaw_events_token}"
    response = httpx.post(endpoint, json=event, headers=headers, timeout=15)
    response.raise_for_status()


def _devices(db: Session) -> list[LifeDevice]:
    return list(
        db.scalars(
            select(LifeDevice).where(
                LifeDevice.deviceKind == "computer", LifeDevice.stat == "active"
            )
        )
    )


def dispatch_hourly_analyses(
    db: Session, *, settings: Settings, now: datetime, post_event: PostEvent | None = None
) -> dict[str, int]:
    timezone = ZoneInfo(settings.computer_analysis_timezone)
    local_now = now.astimezone(timezone)
    hour_start = local_now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    deliver = post_event or (lambda event: _post(settings, event))
    result = {"queued": 0, "skipped": 0, "failed": 0}
    for device in _devices(db):
        row, should_dispatch, _context = queue_hourly_analysis(
            db,
            device=device,
            hour_start=hour_start,
            timezone_name=settings.computer_analysis_timezone,
        )
        if row is None or not should_dispatch:
            result["skipped"] += 1
            continue
        event = {
            "event_id": f"computer-hourly:{device.deviceId}:{row.hourStart}",
            "source": "web",
            "event_type": "computer_hourly_analysis",
            "analysisId": row.analysisId,
            "deviceId": device.deviceId,
            "hourStart": row.hourStart,
            "timezone": settings.computer_analysis_timezone,
            "agentScope": issue_agent_scope(userId=device.userId, purpose="web", ttl_seconds=1800),
        }
        try:
            deliver(event)
            result["queued"] += 1
        except Exception as exc:
            row.status = "failed"
            row.errorMessage = f"adapter dispatch failed: {type(exc).__name__}"
            row.updatedAt = nowIso()
            db.commit()
            result["failed"] += 1
    return result


def dispatch_daily_work_logs(
    db: Session, *, settings: Settings, now: datetime, post_event: PostEvent | None = None
) -> dict[str, int]:
    timezone = ZoneInfo(settings.computer_analysis_timezone)
    log_date = now.astimezone(timezone).date().isoformat()
    deliver = post_event or (lambda event: _post(settings, event))
    result = {"queued": 0, "skipped": 0, "failed": 0}
    for device in _devices(db):
        row, should_dispatch, _context = queue_daily_log(db, device=device, log_date=log_date)
        if row is None or not should_dispatch:
            result["skipped"] += 1
            continue
        event = {
            "event_id": f"computer-daily:{device.deviceId}:{log_date}",
            "source": "web",
            "event_type": "computer_daily_work_log",
            "logId": row.logId,
            "deviceId": device.deviceId,
            "logDate": log_date,
            "agentScope": issue_agent_scope(userId=device.userId, purpose="web", ttl_seconds=1800),
        }
        try:
            deliver(event)
            result["queued"] += 1
        except Exception as exc:
            row.status = "failed"
            row.errorMessage = f"adapter dispatch failed: {type(exc).__name__}"
            row.updatedAt = nowIso()
            db.commit()
            result["failed"] += 1
    return result
