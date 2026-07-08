from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.new_core.models import DeviceStateLog

router = APIRouter(prefix="/api", tags=["device-state"])


def _row_dict(row: DeviceStateLog | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        column.name: getattr(row, column.name)
        for column in row.__table__.columns
    }


def _parse_seen_at(value: str, timezone: ZoneInfo) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone)
    return parsed.astimezone(timezone)


def _split_minutes(hourly: list[float], start: datetime, end: datetime) -> None:
    cursor = start
    while cursor < end:
        next_hour = cursor.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        segment_end = min(end, next_hour)
        hourly[cursor.hour] += (segment_end - cursor).total_seconds() / 60
        cursor = segment_end


@router.get("/devState/latest")
def latest_device_state(
    devId: str = Query(default="pi", min_length=1, max_length=50),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    row = db.scalar(
        select(DeviceStateLog)
        .where(DeviceStateLog.deviceId == devId)
        .order_by(DeviceStateLog.seenAt.desc())
        .limit(1)
    )
    return {"ok": True, "data": _row_dict(row)}


@router.get("/devState/recent")
def recent_device_states(
    devId: str = Query(default="pi", min_length=1, max_length=50),
    limit: int = Query(default=240, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    rows = db.scalars(
        select(DeviceStateLog)
        .where(DeviceStateLog.deviceId == devId)
        .order_by(DeviceStateLog.seenAt.desc())
        .limit(limit)
    ).all()
    return {"ok": True, "data": [_row_dict(row) for row in rows]}


@router.get("/devState/usage/today")
def today_device_usage(
    devId: str = Query(default="pi", min_length=1, max_length=50),
    timezone: str = Query(default="Asia/Shanghai", min_length=1, max_length=64),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        tz = ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("Asia/Shanghai")
        timezone = "Asia/Shanghai"

    now = datetime.now(tz)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    query_start = day_start.isoformat()

    rows = db.scalars(
        select(DeviceStateLog)
        .where(
            DeviceStateLog.deviceId == devId,
            DeviceStateLog.seenAt >= query_start,
        )
        .order_by(DeviceStateLog.seenAt.asc())
        .limit(10000)
    ).all()
    previous = db.scalar(
        select(DeviceStateLog)
        .where(
            DeviceStateLog.deviceId == devId,
            DeviceStateLog.seenAt < query_start,
        )
        .order_by(DeviceStateLog.seenAt.desc())
        .limit(1)
    )

    timeline = ([previous] if previous is not None else []) + list(rows)
    hourly = [0.0] * 24
    confidences: list[float] = []

    for row in rows:
        if row.confidence is not None:
            confidences.append(float(row.confidence))

    for index, row in enumerate(timeline):
        if row.state != "working":
            continue
        start = max(_parse_seen_at(row.seenAt, tz), day_start)
        next_seen = (
            _parse_seen_at(timeline[index + 1].seenAt, tz)
            if index + 1 < len(timeline)
            else now
        )
        raw_end = min(next_seen, now)
        end = min(raw_end, start + timedelta(minutes=2))
        if end > start:
            _split_minutes(hourly, start, end)

    rounded = [round(value, 2) for value in hourly]
    total = round(sum(rounded), 2)
    peak_hour = max(range(24), key=lambda hour: rounded[hour]) if total > 0 else None
    average_confidence = (
        sum(confidences) / len(confidences)
        if confidences
        else None
    )

    return {
        "ok": True,
        "data": {
            "deviceId": devId,
            "timezone": timezone,
            "date": day_start.date().isoformat(),
            "generatedAt": now.isoformat(),
            "hourlyMinutes": rounded,
            "totalMinutes": total,
            "peakHour": peak_hour,
            "averageConfidence": average_confidence,
            "sampleCount": len(rows),
        },
    }
