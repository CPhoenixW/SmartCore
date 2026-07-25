from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import PurePath
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.server.new_core.models import (
    ComputerActivityBucket,
    ComputerActivityContext,
    ComputerActivitySlice,
    ComputerDailyAppUsage,
    ComputerDailyUsage,
    ComputerMonitorStatus,
    DeviceStateLog,
    EvtBase,
    LifeDevice,
    PlanEvt,
    nowIso,
)

STATES = ("active", "idle", "locked", "sleeping", "paused")
SENSITIVE_APP_FRAGMENTS = (
    "1password",
    "bitwarden",
    "dashlane",
    "lastpass",
    "keeper",
    "keepass",
    "passwords",
    "keychain",
    "securityagent",
    "authorizationhost",
    "loginwindow",
)
SENSITIVE_TITLE_FRAGMENTS = (
    "password",
    "passcode",
    "one-time code",
    "two-factor",
    "sign in",
    "banking",
    "payment",
    "密码",
    "验证码",
    "登录",
    "认证",
    "银行",
    "支付",
)
SENSITIVE_DOMAIN_FRAGMENTS = (
    "bank",
    "paypal.",
    "alipay.",
    "stripe.",
    "1password.",
    "bitwarden.",
    "account.apple.",
)


def _aware(value: str | datetime) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include an offset")
    return parsed


def _utc_text(value: str | datetime) -> str:
    return _aware(value).astimezone(UTC).replace(microsecond=0).isoformat()


def _normalized_text(value: str | None, limit: int) -> str | None:
    normalized = " ".join((value or "").split())
    return normalized[:limit] or None


def _contains_fragment(value: str | None, fragments: tuple[str, ...]) -> bool:
    lowered = (value or "").lower()
    return any(fragment in lowered for fragment in fragments)


def _privacy_filtered_title(value: str | None) -> str | None:
    title = _normalized_text(value, 300)
    if not title:
        return None
    parts: list[str] = []
    for part in title.split(" — "):
        parsed = urlsplit(part)
        if parsed.scheme in {"http", "https"} and parsed.hostname:
            parts.append(parsed.hostname.lower())
        elif part.startswith("/") or re.match(r"^[A-Za-z]:\\", part):
            parts.append(PurePath(part.replace("\\", "/")).name)
        else:
            parts.append(part)
    return _normalized_text(" — ".join(parts), 300)


def _sanitize_context(payload: dict[str, Any]) -> dict[str, Any]:
    result = {
        "bundleId": _normalized_text(payload.get("bundleId"), 300) or "unknown",
        "appName": _normalized_text(payload.get("appName"), 200) or "Unknown",
        "windowTitle": _privacy_filtered_title(payload.get("windowTitle")),
        "contextKind": payload.get("contextKind"),
        "domain": _normalized_text(payload.get("domain"), 253),
        "workspace": _normalized_text(payload.get("workspace"), 300),
        "documentName": _normalized_text(payload.get("documentName"), 300),
        "titleRedacted": bool(payload.get("titleRedacted")),
    }
    sensitive = (
        _contains_fragment(result["bundleId"], SENSITIVE_APP_FRAGMENTS)
        or _contains_fragment(result["appName"], SENSITIVE_APP_FRAGMENTS)
        or _contains_fragment(result["windowTitle"], SENSITIVE_TITLE_FRAGMENTS)
        or _contains_fragment(result["domain"], SENSITIVE_DOMAIN_FRAGMENTS)
    )
    if sensitive or result["titleRedacted"]:
        result.update(
            windowTitle=None,
            contextKind=None,
            domain=None,
            workspace=None,
            documentName=None,
            titleRedacted=True,
        )
    return result


def _fingerprint(context: dict[str, Any]) -> str:
    values = (
        context["bundleId"],
        context["windowTitle"],
        context["contextKind"],
        context["domain"],
        context["workspace"],
        context["documentName"],
        context["titleRedacted"],
    )
    return hashlib.sha256("\0".join(str(value or "") for value in values).encode()).hexdigest()


def _context_dict(row: ComputerActivityContext) -> dict[str, Any]:
    return {
        "contextId": row.contextId,
        "bundleId": row.bundleId,
        "appName": row.appName,
        "windowTitle": row.windowTitle,
        "contextKind": row.contextKind,
        "domain": row.domain,
        "workspace": row.workspace,
        "documentName": row.documentName,
        "titleRedacted": row.titleRedacted,
        "classification": None,
    }


def _resolve_context(
    db: Session,
    *,
    user_id: str,
    payload: dict[str, Any],
    seen_at: str,
) -> ComputerActivityContext:
    context = _sanitize_context(payload)
    fingerprint = _fingerprint(context)
    row = db.scalar(
        select(ComputerActivityContext).where(
            ComputerActivityContext.userId == user_id,
            ComputerActivityContext.fingerprint == fingerprint,
        )
    )
    if row is None:
        row = ComputerActivityContext(
            userId=user_id,
            fingerprint=fingerprint,
            bundleId=context["bundleId"],
            appName=context["appName"],
            windowTitle=context["windowTitle"],
            contextKind=context["contextKind"],
            domain=context["domain"],
            workspace=context["workspace"],
            documentName=context["documentName"],
            titleRedacted=context["titleRedacted"],
            firstSeenAt=seen_at,
            lastSeenAt=seen_at,
        )
        db.add(row)
        db.flush()
    else:
        row.appName = context["appName"]
        row.lastSeenAt = max(row.lastSeenAt, seen_at)
    return row


def _recompute_daily(db: Session, *, device: LifeDevice, local_date: str) -> None:
    buckets = list(
        db.scalars(
            select(ComputerActivityBucket).where(
                ComputerActivityBucket.deviceId == device.deviceId,
                ComputerActivityBucket.localDate == local_date,
            )
        )
    )
    bucket_ids = [row.bucketId for row in buckets]
    totals = {state: 0 for state in STATES}
    apps: dict[str, dict[str, Any]] = {}
    if bucket_ids:
        rows = db.execute(
            select(ComputerActivitySlice, ComputerActivityContext)
            .outerjoin(
                ComputerActivityContext,
                ComputerActivityContext.contextId == ComputerActivitySlice.contextId,
            )
            .where(ComputerActivitySlice.bucketId.in_(bucket_ids))
        ).all()
        for activity_slice, context in rows:
            totals[activity_slice.state] += activity_slice.seconds
            if activity_slice.state == "active" and context is not None:
                item = apps.setdefault(
                    context.bundleId,
                    {"appName": context.appName, "seconds": 0},
                )
                item["appName"] = context.appName
                item["seconds"] += activity_slice.seconds

    daily = db.scalar(
        select(ComputerDailyUsage).where(
            ComputerDailyUsage.deviceId == device.deviceId,
            ComputerDailyUsage.usageDate == local_date,
        )
    )
    if daily is None:
        daily = ComputerDailyUsage(
            userId=device.userId,
            deviceId=device.deviceId,
            usageDate=local_date,
        )
        db.add(daily)
        db.flush()
    daily.activeSeconds = totals["active"]
    daily.idleSeconds = totals["idle"]
    daily.lockedSeconds = totals["locked"]
    daily.sleepingSeconds = totals["sleeping"]
    daily.pausedSeconds = totals["paused"]
    daily.switchCount = sum(row.switchCount for row in buckets)
    daily.updatedAt = nowIso()
    db.execute(delete(ComputerDailyAppUsage).where(ComputerDailyAppUsage.dailyUsageId == daily.dailyUsageId))
    for bundle_id, item in apps.items():
        db.add(
            ComputerDailyAppUsage(
                dailyUsageId=daily.dailyUsageId,
                bundleId=bundle_id,
                appName=item["appName"],
                activeSeconds=item["seconds"],
            )
        )


def ingest_activity(
    db: Session,
    *,
    device: LifeDevice,
    schema_version: int,
    buckets: list[dict[str, Any]],
) -> list[str]:
    accepted: list[str] = []
    affected_dates: set[str] = set()
    for item in buckets:
        bucket_start = _utc_text(item["bucketStart"])
        timezone_name = item["timezone"]
        local_date = _aware(bucket_start).astimezone(ZoneInfo(timezone_name)).date().isoformat()
        existing = db.scalar(
            select(ComputerActivityBucket).where(
                ComputerActivityBucket.deviceId == device.deviceId,
                ComputerActivityBucket.bucketStart == bucket_start,
            )
        )
        if existing is None:
            existing = ComputerActivityBucket(
                userId=device.userId,
                deviceId=device.deviceId,
                bucketStart=bucket_start,
            )
            db.add(existing)
        else:
            affected_dates.add(existing.localDate)
            db.execute(delete(ComputerActivitySlice).where(ComputerActivitySlice.bucketId == existing.bucketId))
        existing.sessionId = item.get("sessionId")
        existing.timezone = timezone_name
        existing.localDate = local_date
        existing.coveredSeconds = item["coveredSeconds"]
        existing.switchCount = item["switchCount"]
        existing.schemaVersion = schema_version
        existing.receivedAt = nowIso()
        db.flush()
        for slice_item in item["slices"]:
            context_id = None
            if slice_item["state"] == "active":
                context = _resolve_context(
                    db,
                    user_id=device.userId,
                    payload=slice_item,
                    seen_at=bucket_start,
                )
                context_id = context.contextId
            db.add(
                ComputerActivitySlice(
                    bucketId=existing.bucketId,
                    contextId=context_id,
                    state=slice_item["state"],
                    seconds=slice_item["seconds"],
                )
            )
        affected_dates.add(local_date)
        accepted.append(bucket_start)
    db.flush()
    for local_date in affected_dates:
        _recompute_daily(db, device=device, local_date=local_date)
    db.commit()
    return accepted


def record_heartbeat(db: Session, *, device: LifeDevice, payload: dict[str, Any]) -> dict[str, Any]:
    row = db.get(ComputerMonitorStatus, device.deviceId)
    heartbeat_at = nowIso()
    if row is None:
        row = ComputerMonitorStatus(deviceId=device.deviceId, userId=device.userId)
        db.add(row)
    previous_state = row.currentState
    row.currentState = payload["currentState"]
    heartbeat_context = _sanitize_context(
        {
            "bundleId": "heartbeat",
            "appName": payload.get("currentAppName"),
            "windowTitle": payload.get("currentWindowTitle"),
        }
    )
    row.currentAppName = (
        heartbeat_context["appName"]
        if row.currentState == "active" and payload.get("currentAppName")
        else None
    )
    row.currentWindowTitle = heartbeat_context["windowTitle"] if row.currentState == "active" else None
    row.observedAt = _utc_text(payload["observedAt"])
    row.appVersion = payload["appVersion"]
    row.osVersion = payload["osVersion"]
    row.accessibilityGranted = payload["accessibilityGranted"]
    row.paused = row.currentState == "paused"
    row.queueDepth = payload["queueDepth"]
    row.lastHeartbeatAt = heartbeat_at
    if previous_state != row.currentState or not row.stateSince:
        row.stateSince = row.observedAt
    device.lastSeenAt = heartbeat_at
    db.commit()
    db.refresh(row)
    return monitor_status_dict(row)


def monitor_status_dict(row: ComputerMonitorStatus | None) -> dict[str, Any] | None:
    if row is None:
        return None
    heartbeat = _aware(row.lastHeartbeatAt)
    stale = datetime.now(heartbeat.tzinfo) - heartbeat > timedelta(seconds=120)
    state = "offline" if stale else ("paused" if row.paused else row.currentState)
    return {
        "deviceId": row.deviceId,
        "state": state,
        "reportedState": row.currentState,
        "stateSince": row.lastHeartbeatAt if stale else row.stateSince,
        "observedAt": row.observedAt,
        "currentAppName": row.currentAppName if state == "active" else None,
        "currentWindowTitle": row.currentWindowTitle if state == "active" else None,
        "appVersion": row.appVersion,
        "osVersion": row.osVersion,
        "accessibilityGranted": row.accessibilityGranted,
        "paused": row.paused,
        "queueDepth": row.queueDepth,
        "lastHeartbeatAt": row.lastHeartbeatAt,
        "stale": stale,
    }


def _current_plans(db: Session, *, user_id: str, at: datetime) -> list[dict[str, Any]]:
    rows = db.execute(
        select(EvtBase, PlanEvt)
        .join(PlanEvt, PlanEvt.evtId == EvtBase.evtId)
        .where(EvtBase.userId == user_id, EvtBase.stat != "cancelled")
    ).all()
    result: list[dict[str, Any]] = []
    for base, plan in rows:
        try:
            start = _aware(plan.stTime).astimezone(UTC)
        except (TypeError, ValueError):
            continue
        end = start + timedelta(minutes=plan.durationMin)
        if start <= at < end:
            result.append(
                {
                    "evtId": base.evtId,
                    "title": base.title,
                    "startAt": start.isoformat(),
                    "endAt": end.isoformat(),
                }
            )
    return sorted(result, key=lambda item: item["startAt"], reverse=True)


def _current_presence(db: Session, *, user_id: str, at: datetime) -> dict[str, Any] | None:
    device_ids = list(
        db.scalars(
            select(LifeDevice.deviceId).where(
                LifeDevice.userId == user_id,
                LifeDevice.deviceKind.in_(("pi", "raspberryPi")),
                LifeDevice.stat == "active",
            )
        )
    )
    if not device_ids:
        return None
    row = db.scalar(
        select(DeviceStateLog)
        .where(DeviceStateLog.deviceId.in_(device_ids))
        .order_by(DeviceStateLog.seenAt.desc())
    )
    if row is None:
        return None
    try:
        observed_at = _aware(row.seenAt).astimezone(UTC)
    except ValueError:
        return None
    if at - observed_at > timedelta(seconds=120):
        return None
    meta = row.meta if isinstance(row.meta, dict) else {}
    present = meta.get("present") if isinstance(meta.get("present"), bool) else None
    if present is None and row.state in {"working", "away"}:
        present = row.state == "working"
    return {
        "deviceId": row.deviceId,
        "state": row.state,
        "present": present,
        "observedAt": row.seenAt,
    }


def _current_analysis(db: Session, *, device: LifeDevice, status: dict[str, Any]) -> dict[str, Any]:
    computed_at = datetime.now(UTC)
    plans = _current_plans(db, user_id=device.userId, at=computed_at)
    plan = plans[0] if plans else None
    presence = _current_presence(db, user_id=device.userId, at=computed_at)
    computer_state = status["state"]
    reason_codes = [f"computer.{computer_state}"]
    confidence = "high"

    if computer_state == "offline":
        analysis_state = "unknown"
        confidence = "low"
    elif computer_state == "active" and plan is not None:
        analysis_state = "plan_active"
        reason_codes.append("plan.current")
    elif computer_state == "active":
        analysis_state = "computer_active"
    elif computer_state in {"idle", "locked"} and presence and presence["present"] is True:
        analysis_state = "at_desk_inactive"
        reason_codes.append("presence.present")
    elif computer_state in {"idle", "locked"} and presence and presence["present"] is False:
        analysis_state = "away"
        reason_codes.append("presence.away")
    elif computer_state in {"idle", "locked"}:
        analysis_state = "computer_inactive"
        confidence = "medium"
    elif computer_state == "sleeping":
        analysis_state = "computer_sleeping"
    else:
        analysis_state = "monitor_paused"

    return {
        "state": analysis_state,
        "confidence": confidence,
        "reasonCodes": reason_codes,
        "computedAt": computed_at.isoformat(),
        "currentPlan": plan,
        "presence": presence,
        "algorithmVersion": 1,
    }


def monitor_status_with_analysis(db: Session, *, device: LifeDevice) -> dict[str, Any] | None:
    status = monitor_status_dict(db.get(ComputerMonitorStatus, device.deviceId))
    if status is not None:
        status["analysis"] = _current_analysis(db, device=device, status=status)
    return status


def cleanup_activity(db: Session, *, retention_days: int, now: datetime | None = None) -> int:
    if retention_days < 1:
        return 0
    current = now or datetime.now(UTC)
    cutoff = (current.astimezone(UTC) - timedelta(days=retention_days)).replace(microsecond=0).isoformat()
    bucket_ids = list(
        db.scalars(select(ComputerActivityBucket.bucketId).where(ComputerActivityBucket.bucketStart < cutoff))
    )
    if bucket_ids:
        db.execute(delete(ComputerActivitySlice).where(ComputerActivitySlice.bucketId.in_(bucket_ids)))
        db.execute(delete(ComputerActivityBucket).where(ComputerActivityBucket.bucketId.in_(bucket_ids)))
    referenced = select(ComputerActivitySlice.contextId).where(ComputerActivitySlice.contextId.is_not(None))
    db.execute(delete(ComputerActivityContext).where(ComputerActivityContext.contextId.not_in(referenced)))
    db.commit()
    return len(bucket_ids)


def _merge_intervals(intervals: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    merged: list[tuple[datetime, datetime]] = []
    for start, end in sorted(intervals):
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged


def _overlap_seconds(start: datetime, end: datetime, intervals: list[tuple[datetime, datetime]]) -> float:
    return sum(max(0.0, (min(end, other_end) - max(start, other_start)).total_seconds()) for other_start, other_end in intervals)


def usage_report(
    db: Session,
    *,
    device: LifeDevice,
    range_key: str,
    timezone_name: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    local_tz = ZoneInfo(timezone_name)
    local_now = (now or datetime.now(UTC)).astimezone(local_tz)
    days = {"today": 1, "7d": 7, "30d": 30}[range_key]
    start_date = local_now.date() - timedelta(days=days - 1)
    local_start = datetime.combine(start_date, datetime.min.time(), tzinfo=local_tz)
    range_start = local_start.astimezone(UTC)
    range_end = local_now.astimezone(UTC)
    buckets = list(
        db.scalars(
            select(ComputerActivityBucket)
            .where(
                ComputerActivityBucket.deviceId == device.deviceId,
                ComputerActivityBucket.bucketStart >= range_start.isoformat(),
                ComputerActivityBucket.bucketStart <= range_end.isoformat(),
            )
            .order_by(ComputerActivityBucket.bucketStart)
        )
    )
    bucket_ids = [row.bucketId for row in buckets]
    slices_by_bucket: dict[str, list[tuple[ComputerActivitySlice, ComputerActivityContext | None]]] = defaultdict(list)
    if bucket_ids:
        rows = db.execute(
            select(ComputerActivitySlice, ComputerActivityContext)
            .outerjoin(ComputerActivityContext, ComputerActivityContext.contextId == ComputerActivitySlice.contextId)
            .where(ComputerActivitySlice.bucketId.in_(bucket_ids))
        ).all()
        for activity_slice, context in rows:
            slices_by_bucket[activity_slice.bucketId].append((activity_slice, context))

    plan_rows = db.execute(
        select(EvtBase, PlanEvt)
        .join(PlanEvt, PlanEvt.evtId == EvtBase.evtId)
        .where(EvtBase.userId == device.userId, EvtBase.stat != "cancelled")
    ).all()
    plans: list[dict[str, Any]] = []
    plan_intervals: list[tuple[datetime, datetime]] = []
    for base, plan in plan_rows:
        start = _aware(plan.stTime).astimezone(UTC)
        end = start + timedelta(minutes=plan.durationMin)
        if end <= range_start or start >= range_end:
            continue
        plans.append({"evtId": base.evtId, "title": base.title, "startAt": start.isoformat(), "endAt": end.isoformat(), "activeSeconds": 0})
        plan_intervals.append((start, end))
    merged_plans = _merge_intervals(plan_intervals)

    totals = {state: 0 for state in STATES}
    app_totals: dict[str, dict[str, Any]] = {}
    title_totals: dict[str, dict[str, Any]] = {}
    daily_planned: dict[str, int] = defaultdict(int)
    planned_active = 0.0
    timeline: list[dict[str, Any]] = []
    sessions: dict[str, dict[str, Any]] = {}
    for bucket in buckets:
        bucket_start = _aware(bucket.bucketStart).astimezone(UTC)
        bucket_end = bucket_start + timedelta(seconds=60)
        state_totals = {state: 0 for state in STATES}
        dominant: tuple[int, ComputerActivityContext] | None = None
        active_seconds = 0
        for activity_slice, context in slices_by_bucket[bucket.bucketId]:
            totals[activity_slice.state] += activity_slice.seconds
            state_totals[activity_slice.state] += activity_slice.seconds
            if activity_slice.state != "active" or context is None:
                continue
            active_seconds += activity_slice.seconds
            app = app_totals.setdefault(context.bundleId, {"bundleId": context.bundleId, "appName": context.appName, "seconds": 0})
            app["appName"] = context.appName
            app["seconds"] += activity_slice.seconds
            if context.windowTitle:
                title = title_totals.setdefault(
                    context.contextId,
                    {**_context_dict(context), "seconds": 0},
                )
                title["seconds"] += activity_slice.seconds
            if dominant is None or activity_slice.seconds > dominant[0]:
                dominant = (activity_slice.seconds, context)
        fraction = min(1.0, _overlap_seconds(bucket_start, bucket_end, merged_plans) / 60.0)
        bucket_planned = active_seconds * fraction
        planned_active += bucket_planned
        local_bucket_date = bucket_start.astimezone(local_tz).date().isoformat()
        daily_planned[local_bucket_date] += round(bucket_planned)
        for plan_payload, interval in zip(plans, plan_intervals, strict=True):
            plan_payload["activeSeconds"] += round(active_seconds * min(1.0, _overlap_seconds(bucket_start, bucket_end, [interval]) / 60.0))
        if range_key == "today":
            timeline.append(
                {
                    "startAt": bucket.bucketStart,
                    "states": state_totals,
                    "dominantContext": _context_dict(dominant[1]) if dominant else None,
                    "sessionId": bucket.sessionId,
                    "plannedActiveSeconds": round(bucket_planned),
                }
            )
        if bucket.sessionId:
            session = sessions.setdefault(
                bucket.sessionId,
                {
                    "sessionId": bucket.sessionId,
                    "startAt": bucket.bucketStart,
                    "endAt": bucket_end.isoformat(),
                    "activeSeconds": 0,
                    "idleSeconds": 0,
                    "switchCount": 0,
                    "plannedActiveSeconds": 0,
                    "contexts": {},
                    "inference": None,
                },
            )
            session["endAt"] = max(session["endAt"], bucket_end.isoformat())
            session["activeSeconds"] += state_totals["active"]
            session["idleSeconds"] += state_totals["idle"]
            session["switchCount"] += bucket.switchCount
            session["plannedActiveSeconds"] += round(bucket_planned)
            for activity_slice, context in slices_by_bucket[bucket.bucketId]:
                if activity_slice.state == "active" and context is not None:
                    context_item = session["contexts"].setdefault(
                        context.contextId,
                        {**_context_dict(context), "seconds": 0},
                    )
                    context_item["seconds"] += activity_slice.seconds

    daily_rows = list(
        db.scalars(
            select(ComputerDailyUsage)
            .where(
                ComputerDailyUsage.deviceId == device.deviceId,
                ComputerDailyUsage.usageDate >= start_date.isoformat(),
                ComputerDailyUsage.usageDate <= local_now.date().isoformat(),
            )
            .order_by(ComputerDailyUsage.usageDate)
        )
    )
    daily = [
        {
            "date": row.usageDate,
            "activeSeconds": row.activeSeconds,
            "idleSeconds": row.idleSeconds,
            "lockedSeconds": row.lockedSeconds,
            "sleepingSeconds": row.sleepingSeconds,
            "pausedSeconds": row.pausedSeconds,
            "switchCount": row.switchCount,
            "plannedActiveSeconds": daily_planned[row.usageDate],
        }
        for row in daily_rows
    ]
    session_list = []
    if range_key == "today":
        for session in sessions.values():
            session["contexts"] = sorted(session["contexts"].values(), key=lambda item: item["seconds"], reverse=True)
            session_list.append(session)
    status = monitor_status_with_analysis(db, device=device)
    return {
        "deviceId": device.deviceId,
        "range": range_key,
        "timezone": timezone_name,
        "windowStart": range_start.isoformat(),
        "windowEnd": range_end.isoformat(),
        "status": status,
        "totals": {**{f"{state}Seconds": totals[state] for state in STATES}, "plannedActiveSeconds": round(planned_active), "switchCount": sum(row.switchCount for row in buckets)},
        "timeline": timeline,
        "daily": daily,
        "plans": plans,
        "sessions": sorted(session_list, key=lambda item: item["startAt"], reverse=True),
        "applications": sorted(app_totals.values(), key=lambda item: item["seconds"], reverse=True)[:20],
        "titles": sorted(title_totals.values(), key=lambda item: item["seconds"], reverse=True)[:30],
    }
