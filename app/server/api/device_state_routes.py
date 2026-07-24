from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.server.db.session import get_db
from app.server.new_core.models import DeviceStateLog

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


def _split_minutes(
    hourly: list[float],
    start: datetime,
    end: datetime,
    *,
    window_start: datetime,
) -> None:
    cursor = start
    while cursor < end:
        next_hour = cursor.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        segment_end = min(end, next_hour)
        index = int((cursor - window_start).total_seconds() // 3600)
        if 0 <= index < len(hourly):
            hourly[index] += (segment_end - cursor).total_seconds() / 60
        cursor = segment_end


def _usage_window(
    db: Session,
    *,
    dev_id: str,
    timezone_name: str,
    timezone: ZoneInfo,
    now: datetime,
    window_start: datetime,
    bucket_count: int,
) -> dict[str, Any]:
    query_start = window_start.isoformat()
    rows = db.scalars(
        select(DeviceStateLog)
        .where(
            DeviceStateLog.deviceId == dev_id,
            DeviceStateLog.seenAt >= query_start,
        )
        .order_by(DeviceStateLog.seenAt.asc())
        .limit(10000)
    ).all()
    previous = db.scalar(
        select(DeviceStateLog)
        .where(
            DeviceStateLog.deviceId == dev_id,
            DeviceStateLog.seenAt < query_start,
        )
        .order_by(DeviceStateLog.seenAt.desc())
        .limit(1)
    )

    timeline = ([previous] if previous is not None else []) + list(rows)
    hourly = [0.0] * bucket_count
    confidences = [
        float(row.confidence)
        for row in rows
        if row.confidence is not None
    ]

    for index, row in enumerate(timeline):
        if row.state != "working":
            continue
        start = max(_parse_seen_at(row.seenAt, timezone), window_start)
        next_seen = (
            _parse_seen_at(timeline[index + 1].seenAt, timezone)
            if index + 1 < len(timeline)
            else now
        )
        raw_end = min(next_seen, now)
        end = min(raw_end, start + timedelta(minutes=2))
        if end > start:
            _split_minutes(
                hourly,
                start,
                end,
                window_start=window_start,
            )

    rounded = [round(value, 2) for value in hourly]
    total = round(sum(rounded), 2)
    peak_index = (
        max(range(bucket_count), key=lambda item: rounded[item])
        if total > 0
        else None
    )
    average_confidence = (
        sum(confidences) / len(confidences)
        if confidences
        else None
    )
    points = [
        {
            "startAt": (window_start + timedelta(hours=index)).isoformat(),
            "endAt": (window_start + timedelta(hours=index + 1)).isoformat(),
            "minutes": value,
        }
        for index, value in enumerate(rounded)
    ]
    return {
        "deviceId": dev_id,
        "timezone": timezone_name,
        "windowStart": window_start.isoformat(),
        "windowEnd": now.isoformat(),
        "generatedAt": now.isoformat(),
        "points": points,
        "totalMinutes": total,
        "peakStartAt": (
            points[peak_index]["startAt"]
            if peak_index is not None
            else None
        ),
        "averageConfidence": average_confidence,
        "sampleCount": len(rows),
    }


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
    usage = _usage_window(
        db,
        dev_id=devId,
        timezone_name=timezone,
        timezone=tz,
        now=now,
        window_start=day_start,
        bucket_count=24,
    )
    rounded = [point["minutes"] for point in usage["points"]]
    peak_hour = (
        datetime.fromisoformat(usage["peakStartAt"]).hour
        if usage["peakStartAt"]
        else None
    )

    return {
        "ok": True,
        "data": {
            **usage,
            "date": day_start.date().isoformat(),
            "hourlyMinutes": rounded,
            "peakHour": peak_hour,
        },
    }


@router.get("/devState/usage/recent")
def recent_device_usage(
    devId: str = Query(default="pi", min_length=1, max_length=50),
    timezone: str = Query(default="Asia/Shanghai", min_length=1, max_length=64),
    hours: int = Query(default=12, ge=2, le=48),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        tz = ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("Asia/Shanghai")
        timezone = "Asia/Shanghai"

    now = datetime.now(tz)
    current_hour = now.replace(minute=0, second=0, microsecond=0)
    window_start = current_hour - timedelta(hours=hours - 1)
    usage = _usage_window(
        db,
        dev_id=devId,
        timezone_name=timezone,
        timezone=tz,
        now=now,
        window_start=window_start,
        bucket_count=hours,
    )
    return {"ok": True, "data": {**usage, "rangeHours": hours}}
