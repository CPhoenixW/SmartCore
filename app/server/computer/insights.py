from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.server.computer.contracts import SUPPORTED_COMPUTER_ANALYSIS_MODELS
from app.server.new_core.models import (
    ComputerActivityBucket,
    ComputerActivityContext,
    ComputerActivitySlice,
    ComputerDailyWorkLog,
    ComputerHourlyAnalysis,
    EvtBase,
    LifeDevice,
    NotifyLog,
    PlanEvt,
    newId,
    nowIso,
)
from app.server.new_core.notify import routeNotify

PROMPT_VERSION = "computer-analysis-v1"
DAILY_PROMPT_VERSION = "computer-work-block-v1"
ALLOWED_STATUSES = {"queued", "running", "complete", "failed"}
ALLOWED_PLAN_STATES = {"not_started", "partial", "substantially_executed", "unclear"}
DAILY_LOG_LEASE_SECONDS = 15 * 60
DAILY_LOG_RETRY_DELAYS = (60, 300, 900, 3600)


def _aware(value: str | datetime) -> datetime:
    parsed = (
        value
        if isinstance(value, datetime)
        else datetime.fromisoformat(value.replace("Z", "+00:00"))
    )
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat()


def _overlap(start: datetime, end: datetime, other_start: datetime, other_end: datetime) -> int:
    return max(0, int((min(end, other_end) - max(start, other_start)).total_seconds()))


def _plans(db: Session, *, user_id: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for base, plan in db.execute(
        select(EvtBase, PlanEvt)
        .join(PlanEvt, PlanEvt.evtId == EvtBase.evtId)
        .where(EvtBase.userId == user_id, EvtBase.stat != "cancelled")
    ).all():
        try:
            plan_start = _aware(plan.stTime).astimezone(UTC)
        except (TypeError, ValueError):
            continue
        plan_end = plan_start + timedelta(minutes=plan.durationMin)
        if plan_end <= start or plan_start >= end:
            continue
        result.append(
            {
                "evtId": base.evtId,
                "title": base.title,
                "startAt": _iso(plan_start),
                "endAt": _iso(plan_end),
                "durationSeconds": int((plan_end - plan_start).total_seconds()),
            }
        )
    return sorted(result, key=lambda item: item["startAt"])


def _activity_rows(
    db: Session, *, device: LifeDevice, start: datetime, end: datetime
) -> list[dict[str, Any]]:
    buckets = list(
        db.scalars(
            select(ComputerActivityBucket).where(
                ComputerActivityBucket.deviceId == device.deviceId,
                ComputerActivityBucket.bucketStart >= _iso(start - timedelta(minutes=1)),
                ComputerActivityBucket.bucketStart < _iso(end),
            )
        )
    )
    if not buckets:
        return []
    bucket_ids = [row.bucketId for row in buckets]
    slices = list(
        db.scalars(
            select(ComputerActivitySlice).where(ComputerActivitySlice.bucketId.in_(bucket_ids))
        )
    )
    context_ids = {item.contextId for item in slices if item.contextId}
    contexts = {
        row.contextId: row
        for row in db.scalars(
            select(ComputerActivityContext).where(
                ComputerActivityContext.contextId.in_(context_ids)
            )
        )
    }
    bucket_map = {row.bucketId: _aware(row.bucketStart).astimezone(UTC) for row in buckets}
    output: list[dict[str, Any]] = []
    for item in slices:
        bucket_start = bucket_map[item.bucketId]
        slice_end = bucket_start + timedelta(seconds=item.seconds)
        seconds = _overlap(bucket_start, slice_end, start, end)
        if seconds <= 0:
            continue
        context = contexts.get(item.contextId)
        output.append(
            {
                "state": item.state,
                "seconds": seconds,
                "startAt": _iso(max(bucket_start, start)),
                "sessionId": next(
                    (bucket.sessionId for bucket in buckets if bucket.bucketId == item.bucketId),
                    None,
                ),
                "context": {
                    "contextId": context.contextId,
                    "appName": context.appName,
                    "bundleId": context.bundleId,
                    "windowTitle": context.windowTitle,
                    "contextKind": context.contextKind,
                    "domain": context.domain,
                    "workspace": context.workspace,
                    "documentName": context.documentName,
                }
                if context
                else None,
            }
        )
    return output


def _context_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    totals: dict[str, dict[str, Any]] = {}
    for row in rows:
        context = row.get("context")
        if not context or row["state"] != "active":
            continue
        key = context["contextId"]
        item = totals.setdefault(key, {**context, "seconds": 0, "sessionIds": []})
        item["seconds"] += row["seconds"]
        if row.get("sessionId") and row["sessionId"] not in item["sessionIds"]:
            item["sessionIds"].append(row["sessionId"])
    return sorted(totals.values(), key=lambda item: item["seconds"], reverse=True)[:30]


def build_hour_context(
    db: Session, *, device: LifeDevice, hour_start: datetime, timezone_name: str
) -> dict[str, Any]:
    start = _aware(hour_start).astimezone(UTC)
    end = start + timedelta(hours=1)
    rows = _activity_rows(db, device=device, start=start, end=end)
    plans = _plans(db, user_id=device.userId, start=start, end=end)
    contexts = _context_summary(rows)
    active_seconds = sum(row["seconds"] for row in rows if row["state"] == "active")
    idle_seconds = sum(row["seconds"] for row in rows if row["state"] == "idle")
    for plan in plans:
        plan_start, plan_end = _aware(plan["startAt"]), _aware(plan["endAt"])
        plan["activeSeconds"] = sum(
            _overlap(
                _aware(row["startAt"]),
                _aware(row["startAt"]) + timedelta(seconds=row["seconds"]),
                plan_start,
                plan_end,
            )
            for row in rows
            if row["state"] == "active"
        )
        plan["overlapRatio"] = round(plan["activeSeconds"] / max(1, plan["durationSeconds"]), 3)
    planned_active_seconds = sum(
        max(
            (
                _overlap(
                    _aware(row["startAt"]),
                    _aware(row["startAt"]) + timedelta(seconds=row["seconds"]),
                    _aware(plan["startAt"]),
                    _aware(plan["endAt"]),
                )
                for plan in plans
            ),
            default=0,
        )
        for row in rows
        if row["state"] == "active"
    )
    return {
        "deviceId": device.deviceId,
        "userId": device.userId,
        "hourStart": _iso(start),
        "hourEnd": _iso(end),
        "timezone": timezone_name,
        "localDate": start.astimezone(ZoneInfo(timezone_name)).date().isoformat(),
        "activeSeconds": active_seconds,
        "idleSeconds": idle_seconds,
        "plannedActiveSeconds": planned_active_seconds,
        "plans": plans,
        "contexts": contexts,
        "rows": [
            {
                "state": row["state"],
                "seconds": row["seconds"],
                "startAt": row["startAt"],
                "sessionId": row["sessionId"],
                "contextId": (row["context"] or {}).get("contextId"),
            }
            for row in rows
        ],
    }


def _validate_text(value: Any, *, max_length: int, required: bool = True) -> str | None:
    text = " ".join(str(value or "").split()).strip()
    if required and not text:
        raise ValueError("text is required")
    if len(text) > max_length:
        raise ValueError("text exceeds maximum length")
    return text or None


def _validate_plan_assessments(
    value: Any,
    *,
    plans: list[dict[str, Any]] | None = None,
    active_seconds: int = 0,
    allowed_evt_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 30:
        raise ValueError("planAssessments must be a list of at most 30 items")
    plan_map = {str(plan["evtId"]): plan for plan in plans or []}
    result = []
    for item in value:
        if not isinstance(item, dict) or not item.get("evtId"):
            raise ValueError("plan assessment requires evtId")
        state = str(item.get("state") or "unclear")
        if state not in ALLOWED_PLAN_STATES:
            raise ValueError("invalid plan assessment state")
        evt_id = str(item["evtId"])
        plan = plan_map.get(evt_id)
        if plans is not None and plan is None:
            raise ValueError("plan assessment references a plan outside the context")
        if allowed_evt_ids is not None and evt_id not in allowed_evt_ids:
            raise ValueError("plan assessment references an unknown plan")
        if (
            plans is not None
            and active_seconds <= 0
            and state in {"partial", "substantially_executed"}
        ):
            raise ValueError("a plan cannot be judged executed when activeSeconds is zero")
        if state == "substantially_executed" and float(plan.get("overlapRatio", 0)) < 0.7:
            raise ValueError("substantially_executed requires at least 70% objective overlap")
        assessment = {
            "evtId": evt_id[:64],
            "state": state,
            "confidence": str(item.get("confidence") or "low")[:20],
            "evidenceCodes": [str(code)[:80] for code in item.get("evidenceCodes", [])][:10],
            "note": _validate_text(item.get("note"), max_length=500, required=False),
        }
        if plan is not None:
            assessment.update(
                {
                    "title": plan["title"],
                    "activeSeconds": plan["activeSeconds"],
                    "durationSeconds": plan["durationSeconds"],
                    "overlapRatio": plan["overlapRatio"],
                }
            )
        result.append(assessment)
    return result


def _validate_topics(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 10:
        raise ValueError("topics must be a list of at most 10 items")
    return [
        {
            "name": _validate_text(item.get("name"), max_length=40),
            "summary": _validate_text(item.get("summary"), max_length=300, required=False),
            "activeSeconds": max(0, int(item.get("activeSeconds") or 0)),
            "sessionIds": [str(value)[:64] for value in item.get("sessionIds", [])][:30],
            "contextIds": [str(value)[:64] for value in item.get("contextIds", [])][:30],
        }
        for item in value
        if isinstance(item, dict)
    ]


def queue_hourly_analysis(
    db: Session, *, device: LifeDevice, hour_start: datetime, timezone_name: str
) -> tuple[ComputerHourlyAnalysis | None, bool, dict[str, Any]]:
    context = build_hour_context(
        db, device=device, hour_start=hour_start, timezone_name=timezone_name
    )
    if context["activeSeconds"] == 0 and not context["plans"]:
        return None, False, context
    row = db.scalar(
        select(ComputerHourlyAnalysis).where(
            ComputerHourlyAnalysis.userId == device.userId,
            ComputerHourlyAnalysis.deviceId == device.deviceId,
            ComputerHourlyAnalysis.hourStart == context["hourStart"],
        )
    )
    if row is not None and row.status in {"queued", "running", "complete"}:
        return row, False, context
    now = nowIso()
    if row is None:
        row = ComputerHourlyAnalysis(
            analysisId=newId(),
            userId=device.userId,
            deviceId=device.deviceId,
            hourStart=context["hourStart"],
            hourEnd=context["hourEnd"],
            timezone=timezone_name,
            localDate=context["localDate"],
            activeSeconds=context["activeSeconds"],
            idleSeconds=context["idleSeconds"],
            plannedActiveSeconds=context["plannedActiveSeconds"],
            status="queued",
            createdAt=now,
            updatedAt=now,
        )
        db.add(row)
    else:
        row.status = "queued"
        row.errorMessage = None
        row.updatedAt = now
    db.commit()
    db.refresh(row)
    return row, True, context


def record_hourly_evidence(
    db: Session, *, device: LifeDevice, hour_start: datetime, timezone_name: str
) -> ComputerHourlyAnalysis | None:
    """Persist the immutable hourly objective snapshot without requesting an AI diary entry."""
    context = build_hour_context(
        db, device=device, hour_start=hour_start, timezone_name=timezone_name
    )
    if context["activeSeconds"] == 0 and not context["plans"]:
        return None
    row = db.scalar(
        select(ComputerHourlyAnalysis).where(
            ComputerHourlyAnalysis.userId == device.userId,
            ComputerHourlyAnalysis.deviceId == device.deviceId,
            ComputerHourlyAnalysis.hourStart == context["hourStart"],
        )
    )
    now = nowIso()
    if row is None:
        row = ComputerHourlyAnalysis(
            analysisId=newId(),
            userId=device.userId,
            deviceId=device.deviceId,
            hourStart=context["hourStart"],
            hourEnd=context["hourEnd"],
            timezone=timezone_name,
            localDate=context["localDate"],
            createdAt=now,
            updatedAt=now,
        )
        db.add(row)
    row.activeSeconds = context["activeSeconds"]
    row.idleSeconds = context["idleSeconds"]
    row.plannedActiveSeconds = context["plannedActiveSeconds"]
    if row.promptVersion in {None, "objective-v1"} and not row.title and not row.summary:
        row.status = "complete"
        row.promptVersion = "objective-v1"
        row.generatedAt = now
        row.errorMessage = None
    row.updatedAt = now
    db.commit()
    db.refresh(row)
    return row


def store_hourly_analysis(db: Session, *, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        hour_start = _iso(_aware(payload.get("hourStart")))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("hourStart must be a valid timezone-aware datetime") from exc
    row = db.scalar(
        select(ComputerHourlyAnalysis).where(
            ComputerHourlyAnalysis.userId == user_id,
            ComputerHourlyAnalysis.deviceId == str(payload.get("deviceId")),
            ComputerHourlyAnalysis.hourStart == hour_start,
        )
    )
    if row is None:
        raise ValueError("hourly analysis was not queued")
    device = db.get(LifeDevice, row.deviceId)
    if device is None or device.userId != user_id or device.deviceKind != "computer":
        raise ValueError("computer device not found")
    status = str(payload.get("status") or "complete")
    if status not in {"complete", "failed"}:
        raise ValueError("status must be complete or failed")
    row.status = status
    if status == "complete":
        if payload.get("model") not in SUPPORTED_COMPUTER_ANALYSIS_MODELS:
            raise ValueError("complete analysis must use a supported Computer model")
        if payload.get("promptVersion") not in {None, PROMPT_VERSION}:
            raise ValueError("unsupported prompt version")
    row.title = _validate_text(payload.get("title"), max_length=10, required=status == "complete")
    row.summary = _validate_text(
        payload.get("summary"), max_length=800, required=status == "complete"
    )
    context = build_hour_context(
        db,
        device=device,
        hour_start=_aware(row.hourStart),
        timezone_name=row.timezone,
    )
    row.planAssessments = _validate_plan_assessments(
        payload.get("planAssessments"),
        plans=context["plans"],
        active_seconds=row.activeSeconds,
    )
    row.topics = _validate_topics(payload.get("topics"))
    row.evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
    row.model = _validate_text(payload.get("model"), max_length=100, required=False)
    row.promptVersion = _validate_text(
        payload.get("promptVersion") or PROMPT_VERSION, max_length=40, required=False
    )
    row.errorMessage = _validate_text(payload.get("errorMessage"), max_length=1000, required=False)
    row.generatedAt = nowIso() if status == "complete" else None
    row.updatedAt = nowIso()
    db.commit()
    db.refresh(row)
    return hourly_dict(row)


def hourly_dict(row: ComputerHourlyAnalysis) -> dict[str, Any]:
    return {
        "analysisId": row.analysisId,
        "deviceId": row.deviceId,
        "hourStart": row.hourStart,
        "hourEnd": row.hourEnd,
        "localDate": row.localDate,
        "timezone": row.timezone,
        "activeSeconds": row.activeSeconds,
        "idleSeconds": row.idleSeconds,
        "plannedActiveSeconds": row.plannedActiveSeconds,
        "status": row.status,
        "title": row.title,
        "summary": row.summary,
        "planAssessments": row.planAssessments or [],
        "topics": row.topics or [],
        "evidence": row.evidence or {},
        "model": row.model,
        "promptVersion": row.promptVersion,
        "generatedAt": row.generatedAt,
        "errorMessage": row.errorMessage,
    }


def _daily_log_dict(row: ComputerDailyWorkLog | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "logId": row.logId,
        "deviceId": row.deviceId,
        "logDate": row.logDate,
        "status": row.status,
        "title": row.title,
        "summary": row.summary,
        "topics": row.topics or [],
        "planAssessments": row.planAssessments or [],
        "reminderSummary": row.reminderSummary or [],
        "hourlyAnalysisIds": row.hourlyAnalysisIds or [],
        "workBlockIds": row.workBlockIds or [],
        "phase": row.phase,
        "previewRevision": row.previewRevision,
        "sourceFingerprint": row.sourceFingerprint,
        "finalizedAt": row.finalizedAt,
        "attemptCount": row.attemptCount,
        "lastAttemptAt": row.lastAttemptAt,
        "leaseExpiresAt": row.leaseExpiresAt,
        "nextRetryAt": row.nextRetryAt,
        "model": row.model,
        "promptVersion": row.promptVersion,
        "generatedAt": row.generatedAt,
        "errorMessage": row.errorMessage,
    }


def build_daily_context(db: Session, *, device: LifeDevice, log_date: str) -> dict[str, Any]:
    from app.server.computer.work_blocks import work_block_dict
    from app.server.new_core.models import ComputerWorkBlock

    hours = list(
        db.scalars(
            select(ComputerHourlyAnalysis)
            .where(
                ComputerHourlyAnalysis.deviceId == device.deviceId,
                ComputerHourlyAnalysis.localDate == log_date,
            )
            .order_by(ComputerHourlyAnalysis.hourStart)
        )
    )
    reminders = list(
        db.scalars(
            select(NotifyLog).where(
                NotifyLog.userId == device.userId,
                NotifyLog.dedupKey.like(f"computer-plan-%:{device.deviceId}:%"),
            )
        )
    )
    work_blocks = list(
        db.scalars(
            select(ComputerWorkBlock)
            .where(
                ComputerWorkBlock.userId == device.userId,
                ComputerWorkBlock.deviceId == device.deviceId,
                ComputerWorkBlock.localDate == log_date,
            )
            .order_by(ComputerWorkBlock.startAt)
        )
    )
    return {
        "deviceId": device.deviceId,
        "userId": device.userId,
        "logDate": log_date,
        "hours": [hourly_dict(row) for row in hours],
        "workBlocks": [work_block_dict(row) for row in work_blocks],
        "reminders": [
            {"title": row.title, "content": row.content, "stat": row.stat, "dedupKey": row.dedupKey}
            for row in reminders
            if log_date in row.scheduledAt
        ],
    }


def _daily_log_phase(row: ComputerDailyWorkLog, requested: str) -> str:
    """A finalization request wins over an in-flight preview response."""
    return "final" if requested == "final" or row.phase == "final" else "preview"


def fail_daily_log(
    db: Session,
    *,
    row: ComputerDailyWorkLog,
    error_message: str,
    now: datetime | None = None,
) -> None:
    current = _aware(now or datetime.now(UTC))
    delay = DAILY_LOG_RETRY_DELAYS[
        min(max(0, row.attemptCount - 1), len(DAILY_LOG_RETRY_DELAYS) - 1)
    ]
    row.status = "failed"
    row.leaseExpiresAt = None
    row.nextRetryAt = _iso(current + timedelta(seconds=delay))
    row.errorMessage = _validate_text(error_message, max_length=1000, required=False)
    row.updatedAt = nowIso()
    db.commit()


def mark_daily_log_dispatched(
    db: Session, *, row: ComputerDailyWorkLog, now: datetime
) -> None:
    current = _aware(now)
    row.status = "running"
    row.attemptCount += 1
    row.lastAttemptAt = _iso(current)
    row.leaseExpiresAt = _iso(current + timedelta(seconds=DAILY_LOG_LEASE_SECONDS))
    row.nextRetryAt = None
    row.errorMessage = None
    row.updatedAt = nowIso()
    db.commit()


def queue_daily_log(
    db: Session,
    *,
    device: LifeDevice,
    log_date: str,
    phase: str = "final",
    now: datetime | None = None,
    preview_min_interval_minutes: int = 0,
) -> tuple[ComputerDailyWorkLog | None, bool, dict[str, Any]]:
    if phase not in {"preview", "final"}:
        raise ValueError("daily log phase must be preview or final")
    context = build_daily_context(db, device=device, log_date=log_date)
    if not context["hours"] and not context["workBlocks"]:
        return None, False, context
    row = db.scalar(
        select(ComputerDailyWorkLog).where(
            ComputerDailyWorkLog.userId == device.userId,
            ComputerDailyWorkLog.deviceId == device.deviceId,
            ComputerDailyWorkLog.logDate == log_date,
        )
    )
    source_fingerprint = hashlib.sha256(
        json.dumps(
            [
                {
                    "blockId": item["blockId"],
                    "status": item["status"],
                    "title": item["title"],
                    "summary": item["summary"],
                    "generatedAt": item["generatedAt"],
                    "planStates": [
                        (plan.get("evtId"), plan.get("state"), plan.get("semanticAlignment"))
                        for plan in item.get("planAssessments", [])
                    ],
                }
                for item in context["workBlocks"]
            ],
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    current = _aware(now or datetime.now(UTC))
    if row is not None:
        if row.phase == "final" and row.status == "complete":
            return row, False, context
        desired_phase = _daily_log_phase(row, phase)
        if row.status in {"queued", "running"}:
            lease_expired = bool(
                row.leaseExpiresAt and _aware(row.leaseExpiresAt) <= current
            )
            legacy_stale = (
                not row.leaseExpiresAt
                and _aware(row.updatedAt) <= current - timedelta(seconds=DAILY_LOG_LEASE_SECONDS)
            )
            if not lease_expired and not legacy_stale:
                if row.phase != desired_phase:
                    row.phase = desired_phase
                    row.updatedAt = nowIso()
                    db.commit()
                return row, False, context
            row.phase = desired_phase
            fail_daily_log(
                db,
                row=row,
                error_message="daily work log lease expired before completion",
                now=current,
            )
        if row.status == "failed" and row.nextRetryAt and _aware(row.nextRetryAt) > current:
            if row.phase != desired_phase:
                row.phase = desired_phase
                row.updatedAt = nowIso()
                db.commit()
            return row, False, context
        if phase == "preview" and row.status == "complete":
            if row.sourceFingerprint == source_fingerprint:
                return row, False, context
            if (
                preview_min_interval_minutes > 0
                and row.generatedAt
                and _aware(row.generatedAt)
                > current - timedelta(minutes=preview_min_interval_minutes)
            ):
                return row, False, context
    now_iso = nowIso()
    if row is None:
        row = ComputerDailyWorkLog(
            logId=newId(),
            userId=device.userId,
            deviceId=device.deviceId,
            logDate=log_date,
            status="queued",
            phase=phase,
            createdAt=now_iso,
            updatedAt=now_iso,
        )
        db.add(row)
    else:
        row.status = "queued"
        row.phase = _daily_log_phase(row, phase)
        row.leaseExpiresAt = None
        row.nextRetryAt = None
        row.errorMessage = None
        row.updatedAt = now_iso
    db.commit()
    db.refresh(row)
    return row, True, context


def store_daily_log(db: Session, *, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    row = db.scalar(
        select(ComputerDailyWorkLog).where(
            ComputerDailyWorkLog.userId == user_id,
            ComputerDailyWorkLog.deviceId == str(payload.get("deviceId")),
            ComputerDailyWorkLog.logDate == str(payload.get("logDate")),
        )
    )
    if row is None:
        raise ValueError("daily work log was not queued")
    device = db.get(LifeDevice, row.deviceId)
    if device is None or device.userId != user_id or device.deviceKind != "computer":
        raise ValueError("computer device not found")
    status = str(payload.get("status") or "complete")
    if status not in {"complete", "failed"}:
        raise ValueError("status must be complete or failed")
    requested_phase = str(payload.get("phase") or row.phase or "final")
    if requested_phase not in {"preview", "final"}:
        raise ValueError("daily log phase must be preview or final")
    if row.status == "complete" and row.phase == "final":
        return _daily_log_dict(row) or {}
    row.phase = _daily_log_phase(row, requested_phase)
    if status == "failed":
        fail_daily_log(
            db,
            row=row,
            error_message=str(payload.get("errorMessage") or "daily work log failed"),
        )
        db.refresh(row)
        return _daily_log_dict(row) or {}
    context = build_daily_context(db, device=device, log_date=row.logDate)
    if status == "complete":
        if payload.get("model") not in SUPPORTED_COMPUTER_ANALYSIS_MODELS:
            raise ValueError("complete daily log must use a supported Computer model")
        if payload.get("promptVersion") not in {PROMPT_VERSION, DAILY_PROMPT_VERSION}:
            raise ValueError("unsupported prompt version")
    row.status = status
    phase = row.phase
    row.title = _validate_text(payload.get("title"), max_length=10, required=status == "complete")
    row.summary = _validate_text(
        payload.get("summary"), max_length=1200, required=status == "complete"
    )
    if row.summary and ("\n" in str(payload.get("summary") or "") or row.summary.startswith("#")):
        raise ValueError("daily summary must be one paragraph without Markdown headings")
    if row.title and row.summary and row.summary.startswith(row.title):
        raise ValueError("daily title must independently summarize instead of prefixing summary")
    row.topics = _validate_topics(payload.get("topics"))
    allowed_plan_ids = {
        str(item.get("evtId"))
        for source in [*context["hours"], *context["workBlocks"]]
        for item in source.get("planAssessments", [])
        if item.get("evtId")
    }
    row.planAssessments = _validate_plan_assessments(
        payload.get("planAssessments"), allowed_evt_ids=allowed_plan_ids
    )
    row.reminderSummary = (
        payload.get("reminderSummary") if isinstance(payload.get("reminderSummary"), list) else []
    )
    row.hourlyAnalysisIds = [str(value)[:32] for value in payload.get("hourlyAnalysisIds", [])][:48]
    allowed_block_ids = {item["blockId"] for item in context["workBlocks"]}
    supplied_block_ids = [str(value)[:32] for value in payload.get("workBlockIds", [])][:100]
    if any(value not in allowed_block_ids for value in supplied_block_ids):
        raise ValueError("daily log references a work block outside the context")
    row.workBlockIds = supplied_block_ids or [item["blockId"] for item in context["workBlocks"]]
    if status == "complete":
        source = [
            {
                "blockId": item["blockId"],
                "status": item["status"],
                "title": item["title"],
                "summary": item["summary"],
                "generatedAt": item["generatedAt"],
                "planStates": [
                    (plan.get("evtId"), plan.get("state"), plan.get("semanticAlignment"))
                    for plan in item.get("planAssessments", [])
                ],
            }
            for item in context["workBlocks"]
        ]
        row.sourceFingerprint = hashlib.sha256(
            json.dumps(source, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        if phase == "preview":
            row.previewRevision += 1
        row.finalizedAt = nowIso() if phase == "final" else None
    row.model = _validate_text(payload.get("model"), max_length=100, required=False)
    row.promptVersion = _validate_text(
        payload.get("promptVersion") or DAILY_PROMPT_VERSION, max_length=40, required=False
    )
    row.errorMessage = _validate_text(payload.get("errorMessage"), max_length=1000, required=False)
    row.leaseExpiresAt = None
    row.nextRetryAt = None
    row.generatedAt = nowIso() if status == "complete" else None
    row.updatedAt = nowIso()
    db.commit()
    db.refresh(row)
    return _daily_log_dict(row) or {}


def insights_report(db: Session, *, device: LifeDevice, log_date: str) -> dict[str, Any]:
    from app.server.computer.work_blocks import work_block_insights
    from app.server.new_core.daily_work_context import build_daily_work_context

    hours = list(
        db.scalars(
            select(ComputerHourlyAnalysis)
            .where(
                ComputerHourlyAnalysis.userId == device.userId,
                ComputerHourlyAnalysis.deviceId == device.deviceId,
                ComputerHourlyAnalysis.localDate == log_date,
            )
            .order_by(ComputerHourlyAnalysis.hourStart)
        )
    )
    log = db.scalar(
        select(ComputerDailyWorkLog).where(
            ComputerDailyWorkLog.userId == device.userId,
            ComputerDailyWorkLog.deviceId == device.deviceId,
            ComputerDailyWorkLog.logDate == log_date,
        )
    )
    block_report = work_block_insights(db, device=device, log_date=log_date)
    topics: dict[str, dict[str, Any]] = {}
    plans: list[dict[str, Any]] = []
    for hour in hours:
        for topic in hour.topics or []:
            item = topics.setdefault(
                topic.get("name", "未命名"), {**topic, "activeSeconds": 0, "hourStarts": []}
            )
            item["activeSeconds"] += int(topic.get("activeSeconds") or 0)
            item["hourStarts"].append(hour.hourStart)
        plans.extend(hour.planAssessments or [])
    if block_report["workBlocks"]:
        topics = {str(item["name"]): item for item in block_report["topics"]}
        plans = block_report["planAssessments"]
    daily_work = build_daily_work_context(
        db,
        user_id=device.userId,
        report_date=log_date,
        timezone_name="Asia/Shanghai",
        device_id=device.deviceId,
    )
    return {
        "deviceId": device.deviceId,
        "date": log_date,
        "hours": [hourly_dict(row) for row in hours],
        "legacyHours": [hourly_dict(row) for row in hours],
        "currentBlock": block_report["currentBlock"],
        "workBlocks": block_report["workBlocks"],
        "topics": list(topics.values()),
        "planAssessments": plans,
        "dailyLog": _daily_log_dict(log),
        "analysisState": block_report["analysisState"],
        "reminders": build_daily_context(db, device=device, log_date=log_date)["reminders"],
        "projects": daily_work["projects"],
        "projectTotals": daily_work["totals"],
    }


def dispatch_smart_plan_reminders(db: Session, *, now: datetime, screen_online: Any) -> int:
    sent = 0
    for device in db.scalars(
        select(LifeDevice).where(LifeDevice.deviceKind == "computer", LifeDevice.stat == "active")
    ):
        for base, plan in db.execute(
            select(EvtBase, PlanEvt)
            .join(PlanEvt, PlanEvt.evtId == EvtBase.evtId)
            .where(EvtBase.userId == device.userId, EvtBase.stat != "cancelled")
        ).all():
            start, end = (
                _aware(plan.stTime),
                _aware(plan.stTime) + timedelta(minutes=plan.durationMin),
            )
            if start + timedelta(minutes=10) <= now < end:
                active = sum(
                    row["seconds"]
                    for row in _activity_rows(db, device=device, start=start, end=now)
                    if row["state"] == "active"
                )
                if active == 0:
                    result = routeNotify(
                        db,
                        title="计划尚未开始",
                        content=f"「{base.title}」开始后 10 分钟仍未检测到电脑活跃。",
                        screenOnline=screen_online(device.userId),
                        dedupKey=f"computer-plan-start:{device.deviceId}:{base.evtId}:{_iso(start)}",
                        evtId=base.evtId,
                        phase="notice",
                        userId=device.userId,
                    )
                    sent += result["stat"] == "sent"
            if end <= now <= end + timedelta(minutes=10):
                active = sum(
                    row["seconds"]
                    for row in _activity_rows(db, device=device, start=start, end=end)
                    if row["state"] == "active"
                )
                if active / max(1, int((end - start).total_seconds())) < 0.3:
                    result = routeNotify(
                        db,
                        title="计划执行偏低",
                        content=f"「{base.title}」本次电脑活跃重叠不足 30%，请检查是否需要调整计划。",
                        screenOnline=screen_online(device.userId),
                        dedupKey=f"computer-plan-low-overlap:{device.deviceId}:{base.evtId}:{_iso(end)}",
                        evtId=base.evtId,
                        phase="notice",
                        userId=device.userId,
                    )
                    sent += result["stat"] == "sent"
    return sent
