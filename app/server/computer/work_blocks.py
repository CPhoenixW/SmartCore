from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.server.computer.contracts import SUPPORTED_COMPUTER_ANALYSIS_MODELS
from app.server.computer.insights import (
    _activity_rows,
    _aware,
    _context_summary,
    _iso,
    _overlap,
    _plans,
    _validate_text,
)
from app.server.new_core.models import (
    ComputerWorkBlock,
    ComputerWorkBlockAnalysisRun,
    LifeDevice,
    newId,
    nowIso,
)

WORK_BLOCK_PROMPT_VERSION = "computer-work-block-v1"
WORK_BLOCK_ACTIONS = {"start", "extend", "switch", "complete", "ignore"}
SERVER_ACTION_BY_TRIGGER = {
    "start": "start",
    "switch": "switch",
    "complete": "complete",
    "plan_change": "extend",
    "refresh": "extend",
}
SEMANTIC_ALIGNMENTS = {"aligned", "partially_aligned", "unrelated", "unclear"}
RETRY_DELAYS = (60, 300, 900, 3600)
MAX_ATTEMPTS = 5
INITIAL_SUMMARY_ACTIVE_SECONDS = 5 * 60
FIRST_REFRESH_ACTIVE_SECONDS = 20 * 60
REFRESH_INTERVAL_ACTIVE_SECONDS = 60 * 60


def server_action_for_trigger(trigger_type: str) -> str:
    """Return the deterministic action for a queued analysis trigger."""
    try:
        return SERVER_ACTION_BY_TRIGGER[str(trigger_type)]
    except KeyError as exc:
        raise ValueError("unsupported work block analysis trigger") from exc


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _now_iso(value: datetime) -> str:
    return _iso(_aware(value))


def _next_refresh_threshold(active_seconds: int) -> int:
    if active_seconds < FIRST_REFRESH_ACTIVE_SECONDS:
        return FIRST_REFRESH_ACTIVE_SECONDS
    completed_intervals = (
        active_seconds - FIRST_REFRESH_ACTIVE_SECONDS
    ) // REFRESH_INTERVAL_ACTIVE_SECONDS
    return FIRST_REFRESH_ACTIVE_SECONDS + (completed_intervals + 1) * REFRESH_INTERVAL_ACTIVE_SECONDS


def _open_block(db: Session, device: LifeDevice) -> ComputerWorkBlock | None:
    return db.scalar(
        select(ComputerWorkBlock)
        .where(
            ComputerWorkBlock.userId == device.userId,
            ComputerWorkBlock.deviceId == device.deviceId,
            ComputerWorkBlock.status == "open",
        )
        .order_by(ComputerWorkBlock.startAt.desc())
    )


def _recent_closed_block(db: Session, device: LifeDevice) -> ComputerWorkBlock | None:
    return db.scalar(
        select(ComputerWorkBlock)
        .where(
            ComputerWorkBlock.userId == device.userId,
            ComputerWorkBlock.deviceId == device.deviceId,
            ComputerWorkBlock.status == "closed",
        )
        .order_by(ComputerWorkBlock.endAt.desc())
    )


def _create_open_block(
    db: Session,
    *,
    device: LifeDevice,
    start: datetime,
    end: datetime,
    timezone_name: str,
    continuation_of_id: str | None,
) -> ComputerWorkBlock:
    block = ComputerWorkBlock(
        blockId=newId(),
        userId=device.userId,
        deviceId=device.deviceId,
        continuationOfId=continuation_of_id,
        startAt=_iso(start),
        timezone=timezone_name,
        localDate=start.astimezone(ZoneInfo(timezone_name)).date().isoformat(),
        status="open",
        createdAt=nowIso(),
        updatedAt=nowIso(),
    )
    db.add(block)
    db.flush()
    refresh_work_block(db, block=block, device=device, end=end)
    evidence = dict(block.evidence or {})
    evidence["topicContextIds"] = list(block.contextIds or [])[:8]
    block.evidence = evidence
    db.commit()
    db.refresh(block)
    return block


def _close_work_block(
    db: Session,
    *,
    block: ComputerWorkBlock,
    device: LifeDevice,
    close_at: datetime,
) -> None:
    if block.status == "closed":
        return
    effective_end = max(_aware(block.startAt), _aware(close_at))
    refresh_work_block(db, block=block, device=device, end=effective_end)
    block.status = "closed"
    block.endAt = _iso(effective_end)
    block.updatedAt = nowIso()
    db.commit()


def _active_streak_start(rows: list[dict[str, Any]], *, now: datetime) -> datetime | None:
    """Return the start of the latest continuous active streak once it reaches five minutes."""
    minutes: dict[datetime, dict[str, int]] = {}
    for row in rows:
        bucket_start = _aware(row["startAt"]).replace(second=0, microsecond=0)
        states = minutes.setdefault(bucket_start, {})
        state = str(row.get("state") or "")
        states[state] = states.get(state, 0) + int(row.get("seconds") or 0)
    if not minutes:
        return None
    ordered = sorted(minutes)
    latest_start = ordered[-1]
    latest_states = minutes[latest_start]
    latest_end = latest_start + timedelta(seconds=max(1, sum(latest_states.values())))
    if latest_states.get("active", 0) <= 0 or now - latest_end > timedelta(minutes=2):
        return None
    active_seconds = 0
    streak_start = latest_start
    next_start = latest_start + timedelta(minutes=1)
    for bucket_start in reversed(ordered):
        if next_start - bucket_start > timedelta(minutes=1, seconds=5):
            break
        states = minutes[bucket_start]
        if states.get("active", 0) <= 0 or any(
            states.get(state, 0) > 0 for state in {"locked", "sleeping", "paused"}
        ):
            break
        active_seconds += states["active"]
        streak_start = bucket_start
        next_start = bucket_start
    return streak_start if active_seconds >= INITIAL_SUMMARY_ACTIVE_SECONDS else None


def _objective_plan_state(active_seconds: int, elapsed_seconds: int, alignment: str) -> str:
    ratio = active_seconds / max(1, elapsed_seconds)
    if active_seconds == 0:
        return "not_started" if elapsed_seconds >= 600 else "unclear"
    if ratio >= 0.7 and alignment == "aligned":
        return "substantially_executed"
    if alignment in {"aligned", "partially_aligned"}:
        return "partial"
    return "unclear"


def _plan_metrics(
    db: Session,
    *,
    device: LifeDevice,
    start: datetime,
    end: datetime,
    semantic_by_id: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    semantic_by_id = semantic_by_id or {}
    output: list[dict[str, Any]] = []
    for plan in _plans(db, user_id=device.userId, start=start, end=end):
        plan_start = _aware(plan["startAt"])
        plan_end = _aware(plan["endAt"])
        measured_end = min(plan_end, end)
        elapsed_seconds = max(0, int((measured_end - plan_start).total_seconds()))
        plan_rows = _activity_rows(db, device=device, start=plan_start, end=measured_end)
        active_seconds = sum(row["seconds"] for row in plan_rows if row["state"] == "active")
        semantic = semantic_by_id.get(str(plan["evtId"]), {})
        alignment = str(semantic.get("semanticAlignment") or "unclear")
        if alignment not in SEMANTIC_ALIGNMENTS:
            alignment = "unclear"
        output.append(
            {
                "evtId": plan["evtId"],
                "title": plan["title"],
                "startAt": plan["startAt"],
                "endAt": plan["endAt"],
                "activeSeconds": active_seconds,
                "elapsedSeconds": elapsed_seconds,
                "durationSeconds": plan["durationSeconds"],
                "overlapRatio": round(active_seconds / max(1, elapsed_seconds), 3),
                "semanticAlignment": alignment,
                "state": _objective_plan_state(active_seconds, elapsed_seconds, alignment),
                "confidence": semantic.get("confidence") or "low",
                "evidenceCodes": semantic.get("evidenceCodes") or [],
                "note": semantic.get("note"),
            }
        )
    return output


def _primary_apps(contexts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    totals: dict[str, dict[str, Any]] = {}
    for item in contexts:
        key = str(item.get("bundleId") or item.get("appName") or "unknown")
        row = totals.setdefault(
            key,
            {"bundleId": item.get("bundleId"), "appName": item.get("appName"), "seconds": 0},
        )
        row["seconds"] += int(item.get("seconds") or 0)
    return sorted(totals.values(), key=lambda item: item["seconds"], reverse=True)[:8]


def refresh_work_block(
    db: Session, *, block: ComputerWorkBlock, device: LifeDevice, end: datetime
) -> None:
    start = _aware(block.startAt)
    rows = _activity_rows(db, device=device, start=start, end=end)
    contexts = _context_summary(rows)
    plans = _plans(db, user_id=device.userId, start=start, end=end)
    block.activeSeconds = sum(row["seconds"] for row in rows if row["state"] == "active")
    block.idleSeconds = sum(row["seconds"] for row in rows if row["state"] == "idle")
    block.plannedActiveSeconds = sum(
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
    block.sessionIds = list(
        dict.fromkeys(row["sessionId"] for row in rows if row.get("sessionId"))
    )[:100]
    block.contextIds = [item["contextId"] for item in contexts][:100]
    block.hourStarts = list(
        dict.fromkeys(
            _iso(_aware(row["startAt"]).replace(minute=0, second=0, microsecond=0)) for row in rows
        )
    )[:48]
    block.primaryApps = _primary_apps(contexts)
    semantic = {
        str(item.get("evtId")): item
        for item in block.planAssessments or []
        if isinstance(item, dict) and item.get("evtId")
    }
    block.planAssessments = _plan_metrics(
        db, device=device, start=start, end=end, semantic_by_id=semantic
    )
    trailing = _context_summary(
        [row for row in rows if _aware(row["startAt"]) >= end - timedelta(minutes=30)]
    )
    evidence = dict(block.evidence or {})
    evidence.update(
        {
            "lastObservedAt": _iso(end),
            "trailingContextIds": [item["contextId"] for item in trailing[:8]],
            "dataComplete": bool(rows),
        }
    )
    block.evidence = evidence
    block.updatedAt = nowIso()


def work_block_dict(row: ComputerWorkBlock) -> dict[str, Any]:
    return {
        "blockId": row.blockId,
        "deviceId": row.deviceId,
        "continuationOfId": row.continuationOfId,
        "startAt": row.startAt,
        "endAt": row.endAt,
        "timezone": row.timezone,
        "localDate": row.localDate,
        "status": row.status,
        "topicKey": row.topicKey,
        "title": row.title,
        "summary": row.summary,
        "progress": row.progress,
        "outcome": row.outcome,
        "blocker": row.blocker,
        "nextStep": row.nextStep,
        "activeSeconds": row.activeSeconds,
        "idleSeconds": row.idleSeconds,
        "plannedActiveSeconds": row.plannedActiveSeconds,
        "sessionIds": row.sessionIds or [],
        "contextIds": row.contextIds or [],
        "hourStarts": row.hourStarts or [],
        "primaryApps": row.primaryApps or [],
        "planAssessments": row.planAssessments or [],
        "evidence": row.evidence or {},
        "model": row.model,
        "promptVersion": row.promptVersion,
        "generatedAt": row.generatedAt,
        "updatedAt": row.updatedAt,
    }


def analysis_run_dict(row: ComputerWorkBlockAnalysisRun) -> dict[str, Any]:
    return {
        "runId": row.runId,
        "deviceId": row.deviceId,
        "blockId": row.blockId,
        "triggerType": row.triggerType,
        "status": row.status,
        "attemptCount": row.attemptCount,
        "lastAttemptAt": row.lastAttemptAt,
        "nextRetryAt": row.nextRetryAt,
        "action": row.action,
        "errorMessage": row.errorMessage,
        "updatedAt": row.updatedAt,
    }


def _queue_run(
    db: Session,
    *,
    device: LifeDevice,
    block: ComputerWorkBlock | None,
    trigger_type: str,
    trigger_data: dict[str, Any],
    window_start: datetime,
    window_end: datetime,
    timezone_name: str,
    now: datetime,
) -> tuple[ComputerWorkBlockAnalysisRun, bool]:
    input_fingerprint = _fingerprint(
        {
            "blockId": block.blockId if block else None,
            "triggerType": trigger_type,
            "triggerData": trigger_data,
            "windowStart": _iso(window_start),
            "windowEnd": _iso(window_end),
        }
    )
    trigger_identity: dict[str, Any] = {
        "blockId": block.blockId if block else device.deviceId,
        "triggerType": trigger_type,
    }
    if trigger_type == "switch":
        trigger_identity.update(
            {
                "candidateContextId": trigger_data.get("candidateContextId"),
                "currentTopicContextIds": trigger_data.get("currentTopicContextIds", []),
            }
        )
    elif trigger_type == "plan_change":
        trigger_identity["planIds"] = sorted(
            str(value) for value in trigger_data.get("planIds", [])
        )
        trigger_identity["planPhases"] = trigger_data.get("planPhases", {})
        trigger_identity["planSignatures"] = trigger_data.get("planSignatures", {})
    elif trigger_type == "complete":
        trigger_identity.update(
            {"closeAt": trigger_data.get("closeAt"), "reason": trigger_data.get("reason")}
        )
    elif trigger_type == "refresh":
        trigger_identity["activeThreshold"] = int(trigger_data.get("activeThreshold") or 0)
    trigger_fingerprint = _fingerprint(trigger_identity)
    trigger_key = (
        f"{trigger_type}:{block.blockId if block else device.deviceId}:{trigger_fingerprint[:24]}"
    )
    row = db.scalar(
        select(ComputerWorkBlockAnalysisRun).where(
            ComputerWorkBlockAnalysisRun.userId == device.userId,
            ComputerWorkBlockAnalysisRun.deviceId == device.deviceId,
            ComputerWorkBlockAnalysisRun.triggerKey == trigger_key,
        )
    )
    if row is None:
        row = ComputerWorkBlockAnalysisRun(
            runId=newId(),
            userId=device.userId,
            deviceId=device.deviceId,
            blockId=block.blockId if block else None,
            triggerKey=trigger_key,
            triggerType=trigger_type,
            triggerData=trigger_data,
            windowStart=_iso(window_start),
            windowEnd=_iso(window_end),
            timezone=timezone_name,
            localDate=window_start.astimezone(ZoneInfo(timezone_name)).date().isoformat(),
            inputFingerprint=input_fingerprint,
            status="queued",
            createdAt=nowIso(),
            updatedAt=nowIso(),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row, True
    if row.status == "complete" or row.attemptCount >= MAX_ATTEMPTS:
        return row, False
    return row, _prepare_run_for_dispatch(db, row=row, now=now)


def _prepare_run_for_dispatch(
    db: Session, *, row: ComputerWorkBlockAnalysisRun, now: datetime
) -> bool:
    if row.status == "complete" or row.attemptCount >= MAX_ATTEMPTS:
        return False
    stale_queued = (
        row.status == "queued"
        and row.attemptCount > 0
        and (not row.lastAttemptAt or _aware(row.lastAttemptAt) <= now - timedelta(minutes=10))
    )
    stale_running = (
        row.status == "running"
        and (not row.leaseExpiresAt or _aware(row.leaseExpiresAt) <= now)
    )
    retry_due = (
        row.status == "failed"
        and row.nextRetryAt is not None
        and _aware(row.nextRetryAt) <= now
    )
    if row.status == "queued" and row.attemptCount == 0:
        db.commit()
        return True
    if stale_queued or stale_running or retry_due:
        row.status = "queued"
        row.leaseExpiresAt = None
        row.nextRetryAt = None
        row.updatedAt = nowIso()
        db.commit()
        return True
    db.commit()
    return False


def _next_dispatchable_run(
    db: Session, *, device: LifeDevice, now: datetime
) -> ComputerWorkBlockAnalysisRun | None:
    rows = list(
        db.scalars(
            select(ComputerWorkBlockAnalysisRun)
            .where(
                ComputerWorkBlockAnalysisRun.userId == device.userId,
                ComputerWorkBlockAnalysisRun.deviceId == device.deviceId,
                ComputerWorkBlockAnalysisRun.status != "complete",
                ComputerWorkBlockAnalysisRun.attemptCount < MAX_ATTEMPTS,
            )
            .order_by(ComputerWorkBlockAnalysisRun.createdAt)
        )
    )
    for row in rows:
        if _prepare_run_for_dispatch(db, row=row, now=now):
            return row
    return None


def _has_inflight_run(
    db: Session, *, device: LifeDevice, block: ComputerWorkBlock
) -> bool:
    return (
        db.scalar(
            select(ComputerWorkBlockAnalysisRun.runId).where(
                ComputerWorkBlockAnalysisRun.userId == device.userId,
                ComputerWorkBlockAnalysisRun.deviceId == device.deviceId,
                ComputerWorkBlockAnalysisRun.blockId == block.blockId,
                ComputerWorkBlockAnalysisRun.status.in_({"queued", "running"}),
            )
        )
        is not None
    )


def _queued_result(
    db: Session,
    *,
    device: LifeDevice,
    now: datetime,
    candidate: tuple[ComputerWorkBlockAnalysisRun, bool],
) -> tuple[ComputerWorkBlockAnalysisRun | None, bool]:
    row, should_dispatch = candidate
    if should_dispatch:
        return row, True
    pending = _next_dispatchable_run(db, device=device, now=now)
    return (pending, True) if pending is not None else (row, False)


def evaluate_work_block(
    db: Session,
    *,
    device: LifeDevice,
    now: datetime,
    timezone_name: str,
) -> tuple[ComputerWorkBlockAnalysisRun | None, bool]:
    now = _aware(now).astimezone(UTC)
    local_tz = ZoneInfo(timezone_name)
    block = _open_block(db, device)
    if block is None:
        recent_start = now - timedelta(minutes=10)
        recent = sorted(
            _activity_rows(db, device=device, start=recent_start, end=now),
            key=lambda item: item["startAt"],
        )
        start_at = _active_streak_start(recent, now=now)
        if start_at is None:
            pending = _next_dispatchable_run(db, device=device, now=now)
            return (pending, True) if pending is not None else (None, False)
        previous = _recent_closed_block(db, device)
        continuation = None
        if previous and previous.endAt and now - _aware(previous.endAt) <= timedelta(minutes=30):
            previous_local = _aware(previous.endAt).astimezone(local_tz)
            if previous_local.time().hour == 0 and previous_local.time().minute == 0:
                continuation = previous.blockId
        block = _create_open_block(
            db,
            device=device,
            start=start_at,
            end=now,
            timezone_name=timezone_name,
            continuation_of_id=continuation,
        )
        return _queued_result(
            db,
            device=device,
            now=now,
            candidate=_queue_run(
                db,
                device=device,
                block=block,
                trigger_type="start",
                trigger_data={"continuationOfId": continuation},
                window_start=start_at,
                window_end=now,
                timezone_name=timezone_name,
                now=now,
            ),
        )

    start = _aware(block.startAt)
    block_evidence = dict(block.evidence or {})
    if not block_evidence.get("topicContextIds") and block.contextIds:
        block_evidence["topicContextIds"] = list(block.contextIds)[:8]
        block.evidence = block_evidence
    prior_topic_ids = set(block_evidence.get("topicContextIds") or [])
    refresh_work_block(db, block=block, device=device, end=now)
    db.commit()

    current_local_date = now.astimezone(local_tz).date().isoformat()
    if block.localDate != current_local_date:
        midnight = datetime.combine(
            now.astimezone(local_tz).date(), datetime.min.time(), tzinfo=local_tz
        ).astimezone(UTC)
        _close_work_block(db, block=block, device=device, close_at=midnight)
        return _queued_result(
            db,
            device=device,
            now=now,
            candidate=_queue_run(
                db,
                device=device,
                block=block,
                trigger_type="complete",
                trigger_data={"closeAt": _iso(midnight), "reason": "midnight"},
                window_start=start,
                window_end=midnight,
                timezone_name=timezone_name,
                now=now,
            ),
        )

    rows = sorted(
        _activity_rows(db, device=device, start=max(start, now - timedelta(minutes=30)), end=now),
        key=lambda item: item["startAt"],
    )
    latest = rows[-1] if rows else None
    active_rows = [row for row in rows if row["state"] == "active"]
    last_active_end = max(
        (_aware(row["startAt"]) + timedelta(seconds=row["seconds"]) for row in active_rows),
        default=start,
    )
    if latest and latest["state"] in {"locked", "sleeping", "paused"}:
        close_at = max(start, _aware(latest["startAt"]))
        _close_work_block(db, block=block, device=device, close_at=close_at)
        return _queued_result(
            db,
            device=device,
            now=now,
            candidate=_queue_run(
                db,
                device=device,
                block=block,
                trigger_type="complete",
                trigger_data={"closeAt": _iso(close_at), "reason": latest["state"]},
                window_start=start,
                window_end=close_at,
                timezone_name=timezone_name,
                now=now,
            ),
        )
    if now - last_active_end >= timedelta(minutes=20):
        _close_work_block(db, block=block, device=device, close_at=last_active_end)
        return _queued_result(
            db,
            device=device,
            now=now,
            candidate=_queue_run(
                db,
                device=device,
                block=block,
                trigger_type="complete",
                trigger_data={"closeAt": _iso(last_active_end), "reason": "idle_20m"},
                window_start=start,
                window_end=last_active_end,
                timezone_name=timezone_name,
                now=now,
            ),
        )

    recent_start = now - timedelta(minutes=15)
    recent_rows = [
        row for row in rows if _aware(row["startAt"]) >= recent_start and row["state"] == "active"
    ]
    recent_contexts = _context_summary(recent_rows)
    recent_active = sum(row["seconds"] for row in recent_rows)
    if recent_contexts and recent_active >= 300:
        dominant = recent_contexts[0]
        dominant_share = dominant["seconds"] / max(1, recent_active)
        recent_ids = {item["contextId"] for item in recent_contexts[:5]}
        union = prior_topic_ids | recent_ids
        similarity = len(prior_topic_ids & recent_ids) / max(1, len(union))
        candidate_rows = [
            row
            for row in recent_rows
            if (row.get("context") or {}).get("contextId") == dominant["contextId"]
        ]
        candidate_start = min(
            (_aware(row["startAt"]) for row in candidate_rows), default=recent_start
        )
        if (
            prior_topic_ids
            and dominant_share >= 0.6
            and dominant["contextId"] not in prior_topic_ids
            and similarity < 0.4
            and now - candidate_start >= timedelta(minutes=15)
        ):
            return _queued_result(
                db,
                device=device,
                now=now,
                candidate=_queue_run(
                    db,
                    device=device,
                    block=block,
                    trigger_type="switch",
                    trigger_data={
                        "candidateContextId": dominant["contextId"],
                        "candidateStartAt": _iso(candidate_start),
                        "currentTopicContextIds": sorted(prior_topic_ids)[:8],
                        "similarity": round(similarity, 3),
                    },
                    window_start=start,
                    window_end=now,
                    timezone_name=timezone_name,
                    now=now,
                ),
            )

    analyzed_phases = dict(block_evidence.get("planAnalysisPhases") or {})
    analyzed_signatures = dict(block_evidence.get("planAnalysisSignatures") or {})
    current_phases = {
        str(item["evtId"]): (
            "ended" if now >= _aware(item["endAt"]) else "active"
        )
        for item in block.planAssessments or []
        if isinstance(item, dict) and item.get("evtId") and item.get("endAt")
    }
    current_signatures = {
        str(item["evtId"]): _fingerprint(
            {
                "title": item.get("title"),
                "startAt": item.get("startAt"),
                "endAt": item.get("endAt"),
            }
        )[:16]
        for item in block.planAssessments or []
        if isinstance(item, dict) and item.get("evtId")
    }
    missing_ids = sorted(
        evt_id
        for evt_id, phase in current_phases.items()
        if analyzed_phases.get(evt_id) != phase
        or analyzed_signatures.get(evt_id) != current_signatures.get(evt_id)
    )
    if missing_ids and block.activeSeconds > 0:
        return _queued_result(
            db,
            device=device,
            now=now,
            candidate=_queue_run(
                db,
                device=device,
                block=block,
                trigger_type="plan_change",
                trigger_data={
                    "planIds": missing_ids,
                    "planPhases": {evt_id: current_phases[evt_id] for evt_id in missing_ids},
                    "planSignatures": {
                        evt_id: current_signatures[evt_id] for evt_id in missing_ids
                    },
                },
                window_start=start,
                window_end=now,
                timezone_name=timezone_name,
                now=now,
            ),
        )
    pending = _next_dispatchable_run(db, device=device, now=now)
    if pending is not None:
        return pending, True
    if _has_inflight_run(db, device=device, block=block):
        return None, False
    evidence = dict(block.evidence or {})
    next_refresh = int(
        evidence.get("nextSummaryActiveSeconds") or FIRST_REFRESH_ACTIVE_SECONDS
    )
    if (
        block.status == "open"
        and block.generatedAt
        and next_refresh >= FIRST_REFRESH_ACTIVE_SECONDS
        and block.activeSeconds >= next_refresh
    ):
        return _queued_result(
            db,
            device=device,
            now=now,
            candidate=_queue_run(
                db,
                device=device,
                block=block,
                trigger_type="refresh",
                trigger_data={
                    "activeThreshold": next_refresh,
                    "summaryRevision": int(evidence.get("summaryRevision") or 1) + 1,
                },
                window_start=start,
                window_end=now,
                timezone_name=timezone_name,
                now=now,
            ),
        )
    return None, False


def mark_run_dispatched(db: Session, row: ComputerWorkBlockAnalysisRun, *, now: datetime) -> None:
    if row.attemptCount >= MAX_ATTEMPTS or row.status != "queued":
        raise ValueError("analysis run is not dispatchable")
    row.status = "queued"
    row.attemptCount += 1
    row.lastAttemptAt = _now_iso(now)
    row.leaseExpiresAt = None
    row.nextRetryAt = None
    row.errorMessage = None
    row.updatedAt = nowIso()
    db.commit()


def fail_analysis_run(
    db: Session,
    *,
    row: ComputerWorkBlockAnalysisRun,
    error_message: str,
    now: datetime | None = None,
    retryable: bool = True,
) -> None:
    current = _aware(now or datetime.now(UTC))
    row.status = "failed"
    row.leaseExpiresAt = None
    if not retryable or row.attemptCount >= MAX_ATTEMPTS:
        row.nextRetryAt = None
    else:
        delay_index = min(max(0, row.attemptCount - 1), len(RETRY_DELAYS) - 1)
        row.nextRetryAt = _iso(current + timedelta(seconds=RETRY_DELAYS[delay_index]))
    row.errorMessage = _validate_text(error_message, max_length=1000, required=False)
    row.updatedAt = nowIso()
    db.commit()


def build_work_block_context(
    db: Session, *, device: LifeDevice, run: ComputerWorkBlockAnalysisRun, claim: bool = True
) -> dict[str, Any]:
    if run.deviceId != device.deviceId or run.userId != device.userId:
        raise ValueError("analysis run does not belong to this device")
    if run.status == "complete":
        raise ValueError("analysis run is already complete")
    now = datetime.now(UTC)
    if claim:
        if run.status != "queued" or run.attemptCount < 1:
            raise ValueError("analysis run is not ready to claim")
        claimed = db.execute(
            update(ComputerWorkBlockAnalysisRun)
            .where(
                ComputerWorkBlockAnalysisRun.runId == run.runId,
                ComputerWorkBlockAnalysisRun.status == "queued",
            )
            .values(
                status="running",
                leaseExpiresAt=_iso(now + timedelta(minutes=10)),
                updatedAt=nowIso(),
            )
            .execution_options(synchronize_session=False)
        )
        if claimed.rowcount != 1:
            db.rollback()
            raise ValueError("analysis run is already claimed")
        db.commit()
        db.refresh(run)
    start, end = _aware(run.windowStart), _aware(run.windowEnd)
    rows = _activity_rows(db, device=device, start=start, end=end)
    contexts = _context_summary(rows)
    block = db.get(ComputerWorkBlock, run.blockId) if run.blockId else None
    evidence = dict(block.evidence or {}) if block else {}
    last_summarized_at = evidence.get("lastSummarizedAt")
    incremental_rows = rows
    if last_summarized_at:
        summarized_at = _aware(last_summarized_at)
        incremental_rows = [
            row for row in rows if _aware(row["startAt"]) >= summarized_at
        ]
    incremental_contexts = _context_summary(incremental_rows)
    semantic = {
        str(item.get("evtId")): item
        for item in (block.planAssessments if block else []) or []
        if isinstance(item, dict) and item.get("evtId")
    }
    plans = _plan_metrics(db, device=device, start=start, end=end, semantic_by_id=semantic)
    return {
        "runId": run.runId,
        "deviceId": device.deviceId,
        "triggerType": run.triggerType,
        "triggerData": run.triggerData or {},
        "windowStart": run.windowStart,
        "windowEnd": run.windowEnd,
        "timezone": run.timezone,
        "currentBlock": work_block_dict(block) if block else None,
        "facts": {
            "activeSeconds": sum(row["seconds"] for row in rows if row["state"] == "active"),
            "idleSeconds": sum(row["seconds"] for row in rows if row["state"] == "idle"),
            "contexts": contexts,
            "plans": plans,
            "sessionIds": list(
                dict.fromkeys(row["sessionId"] for row in rows if row.get("sessionId"))
            ),
            "contextIds": [item["contextId"] for item in contexts],
            "incrementalActiveSeconds": sum(
                row["seconds"] for row in incremental_rows if row["state"] == "active"
            ),
            "incrementalContexts": incremental_contexts,
        },
        "constraints": {
            "actions": sorted(WORK_BLOCK_ACTIONS),
            "allowedActionsForTrigger": {
                trigger: [action] for trigger, action in SERVER_ACTION_BY_TRIGGER.items()
            }.get(run.triggerType, []),
            "semanticAlignments": sorted(SEMANTIC_ALIGNMENTS),
            "promptVersion": WORK_BLOCK_PROMPT_VERSION,
            "untrustedContext": True,
        },
    }


def _validate_semantic_assessments(
    value: Any, *, plans: list[dict[str, Any]], required: bool
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("planSemanticAssessments must be a list")
    plan_ids = {str(item["evtId"]) for item in plans}
    provided: dict[str, dict[str, Any]] = {}
    for item in value:
        if not isinstance(item, dict) or not item.get("evtId"):
            raise ValueError("plan semantic assessment requires evtId")
        evt_id = str(item["evtId"])
        if evt_id not in plan_ids:
            raise ValueError("plan semantic assessment references a plan outside the context")
        alignment = str(item.get("semanticAlignment") or "")
        if alignment not in SEMANTIC_ALIGNMENTS:
            raise ValueError("invalid semantic alignment")
        provided[evt_id] = {
            "evtId": evt_id,
            "semanticAlignment": alignment,
            "confidence": str(item.get("confidence") or "low")[:20],
            "evidenceCodes": [str(code)[:80] for code in item.get("evidenceCodes", [])][:10],
            "note": _validate_text(item.get("note"), max_length=500, required=False),
        }
    if required:
        # A missing semantic match is an uncertain match, not a malformed request.
        # Objective overlap and final Plan state remain Server-owned calculations.
        for plan in plans:
            evt_id = str(plan["evtId"])
            provided.setdefault(
                evt_id,
                {
                    "evtId": evt_id,
                    "semanticAlignment": "unclear",
                    "confidence": "low",
                    "evidenceCodes": [],
                    "note": None,
                },
            )
    return [provided[str(plan["evtId"])] for plan in plans if str(plan["evtId"]) in provided]


def _validated_content(payload: dict[str, Any], *, required: bool) -> dict[str, str | None]:
    title = _validate_text(payload.get("title"), max_length=20, required=required)
    summary = _validate_text(payload.get("summary"), max_length=800, required=required)
    if summary and ("\n" in str(payload.get("summary") or "") or summary.startswith("#")):
        raise ValueError("summary must be one paragraph without Markdown headings")
    if title and summary and summary.startswith(title):
        raise ValueError("title must independently summarize instead of prefixing summary")
    return {
        "title": title,
        "summary": summary,
        "progress": _validate_text(payload.get("progress"), max_length=300, required=False),
        "outcome": _validate_text(payload.get("outcome"), max_length=300, required=False),
        "blocker": _validate_text(payload.get("blocker"), max_length=300, required=False),
        "nextStep": _validate_text(payload.get("nextStep"), max_length=300, required=False),
    }


def _apply_content(
    block: ComputerWorkBlock,
    content: dict[str, str | None],
    payload: dict[str, Any],
    *,
    replace_optional: bool = False,
) -> None:
    for field, value in content.items():
        if value is not None or replace_optional:
            setattr(block, field, value)
    topic_key = _validate_text(payload.get("topicKey"), max_length=100, required=False)
    if topic_key:
        block.topicKey = topic_key
    elif not block.topicKey and block.title:
        block.topicKey = block.title.casefold()
    block.model = _validate_text(payload.get("model"), max_length=100)
    block.promptVersion = WORK_BLOCK_PROMPT_VERSION
    block.generatedAt = nowIso()
    block.updatedAt = nowIso()


def store_work_block_analysis(
    db: Session, *, user_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    run = db.get(ComputerWorkBlockAnalysisRun, str(payload.get("runId")))
    if run is None or run.userId != user_id:
        raise ValueError("work block analysis run not found")
    if run.status == "complete":
        block = db.get(ComputerWorkBlock, run.blockId) if run.blockId else None
        return {
            "run": analysis_run_dict(run),
            "workBlock": work_block_dict(block) if block else None,
        }
    device = db.get(LifeDevice, run.deviceId)
    if device is None or device.userId != user_id or device.deviceKind != "computer":
        raise ValueError("computer device not found")
    status = str(payload.get("status") or "complete")
    if status == "failed":
        fail_analysis_run(
            db, row=run, error_message=str(payload.get("errorMessage") or "analysis failed")
        )
        return analysis_run_dict(run)
    if status != "complete":
        raise ValueError("status must be complete or failed")
    if payload.get("model") not in SUPPORTED_COMPUTER_ANALYSIS_MODELS:
        raise ValueError("complete analysis must use a supported Computer model")
    if payload.get("promptVersion") != WORK_BLOCK_PROMPT_VERSION:
        raise ValueError("unsupported prompt version")
    # Keep the request/database field for compatibility and audit output, but
    # always derive the effective action from the Server-owned trigger.
    action = server_action_for_trigger(run.triggerType)
    if not run.blockId:
        raise ValueError("action requires an existing work block")
    context = build_work_block_context(db, device=device, run=run, claim=False)
    required_content = action in {"start", "switch"} or run.triggerType == "refresh"
    content = _validated_content(payload, required=required_content)
    semantics = _validate_semantic_assessments(
        payload.get("planSemanticAssessments", []),
        plans=context["facts"]["plans"],
        required=bool(context["facts"]["plans"]),
    )
    allowed_context_ids = set(context["facts"]["contextIds"])
    evidence_context_ids = [str(value) for value in payload.get("evidenceContextIds", [])]
    if any(value not in allowed_context_ids for value in evidence_context_ids):
        raise ValueError("analysis references context evidence outside the run")
    semantic_map = {str(item["evtId"]): item for item in semantics}
    block = db.get(ComputerWorkBlock, run.blockId) if run.blockId else None
    if block is None or block.userId != user_id or block.deviceId != device.deviceId:
        raise ValueError("work block not found")
    if action == "start":
        if block.status != "open":
            raise ValueError("start analysis requires an open work block")
        _apply_content(block, content, payload)
    elif action == "switch":
        if block.status != "open":
            raise ValueError("switch analysis requires an open work block")
        switch_at = _aware((run.triggerData or {}).get("candidateStartAt") or run.windowEnd)
        refresh_work_block(db, block=block, device=device, end=switch_at)
        block.status = "closed"
        block.endAt = _iso(switch_at)
        block.updatedAt = nowIso()
        new_block = ComputerWorkBlock(
            blockId=newId(),
            userId=user_id,
            deviceId=device.deviceId,
            startAt=_iso(switch_at),
            timezone=run.timezone,
            localDate=switch_at.astimezone(ZoneInfo(run.timezone)).date().isoformat(),
            status="open",
            createdAt=nowIso(),
            updatedAt=nowIso(),
        )
        db.add(new_block)
        db.flush()
        _apply_content(new_block, content, payload)
        block = new_block
        run.blockId = new_block.blockId
    elif action in {"extend", "complete"}:
        _apply_content(
            block,
            content,
            payload,
            replace_optional=run.triggerType == "refresh",
        )
        if action == "extend" and block.status != "open":
            raise ValueError("extend analysis requires an open work block")
        if action == "complete" and block.status != "closed":
            close_at = _aware((run.triggerData or {}).get("closeAt") or run.windowEnd)
            _close_work_block(db, block=block, device=device, close_at=close_at)

    if block is not None:
        effective_end = _aware(block.endAt) if block.endAt else _aware(run.windowEnd)
        refresh_work_block(db, block=block, device=device, end=effective_end)
        block.planAssessments = _plan_metrics(
            db,
            device=device,
            start=_aware(block.startAt),
            end=effective_end,
            semantic_by_id=semantic_map,
        )
        evidence = dict(block.evidence or {})
        evidence["analysisContextIds"] = evidence_context_ids
        evidence["planAnalysisPhases"] = {
            str(item["evtId"]): (
                "ended" if effective_end >= _aware(item["endAt"]) else "active"
            )
            for item in block.planAssessments or []
            if isinstance(item, dict) and item.get("evtId") and item.get("endAt")
        }
        evidence["planAnalysisSignatures"] = {
            str(item["evtId"]): _fingerprint(
                {
                    "title": item.get("title"),
                    "startAt": item.get("startAt"),
                    "endAt": item.get("endAt"),
                }
            )[:16]
            for item in block.planAssessments or []
            if isinstance(item, dict) and item.get("evtId")
        }
        if action in {"start", "switch"} or run.triggerType == "switch":
            evidence["topicContextIds"] = (
                evidence_context_ids or context["facts"]["contextIds"][:8]
            )
        if run.triggerType in {"start", "refresh"} or action == "switch":
            previous_revision = int(evidence.get("summaryRevision") or 0)
            requested_revision = int((run.triggerData or {}).get("summaryRevision") or 0)
            evidence["summaryRevision"] = max(previous_revision + 1, requested_revision, 1)
            evidence["lastSummarizedAt"] = run.windowEnd
            evidence["lastSummarizedActiveSeconds"] = int(block.activeSeconds or 0)
            evidence["nextSummaryActiveSeconds"] = _next_refresh_threshold(
                int(block.activeSeconds or 0)
            )
        block.evidence = evidence
    run.status = "complete"
    run.action = action
    run.leaseExpiresAt = None
    run.nextRetryAt = None
    run.errorMessage = None
    run.completedAt = nowIso()
    run.updatedAt = nowIso()
    db.commit()
    if block is not None:
        db.refresh(block)
    return {"run": analysis_run_dict(run), "workBlock": work_block_dict(block) if block else None}


def work_block_insights(db: Session, *, device: LifeDevice, log_date: str) -> dict[str, Any]:
    blocks = list(
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
    runs = list(
        db.scalars(
            select(ComputerWorkBlockAnalysisRun)
            .where(
                ComputerWorkBlockAnalysisRun.userId == device.userId,
                ComputerWorkBlockAnalysisRun.deviceId == device.deviceId,
                ComputerWorkBlockAnalysisRun.localDate == log_date,
            )
            .order_by(ComputerWorkBlockAnalysisRun.createdAt.desc())
        )
    )
    topics: dict[str, dict[str, Any]] = {}
    plans: dict[str, dict[str, Any]] = {}
    for block in blocks:
        key = block.topicKey or block.title or "未识别主题"
        topic = topics.setdefault(
            key,
            {
                "name": block.title or "未识别主题",
                "summary": block.summary,
                "activeSeconds": 0,
                "blockIds": [],
                "hourStarts": [],
            },
        )
        topic["activeSeconds"] += block.activeSeconds
        topic["blockIds"].append(block.blockId)
        topic["hourStarts"] = list(dict.fromkeys(topic["hourStarts"] + (block.hourStarts or [])))
        if block.summary:
            topic["summary"] = block.summary
        for item in block.planAssessments or []:
            if isinstance(item, dict) and item.get("evtId"):
                plans[str(item["evtId"])] = item
    current = next((row for row in reversed(blocks) if row.status == "open"), None)
    latest_run = runs[0] if runs else None
    return {
        "currentBlock": work_block_dict(current) if current else None,
        "workBlocks": [work_block_dict(row) for row in blocks],
        "topics": list(topics.values()),
        "planAssessments": list(plans.values()),
        "analysisState": analysis_run_dict(latest_run) if latest_run else None,
    }


def cleanup_work_blocks(db: Session, *, retention_days: int, now: datetime | None = None) -> int:
    if retention_days < 1:
        return 0
    cutoff = _iso(_aware(now or datetime.now(UTC)) - timedelta(days=retention_days))
    blocks = list(
        db.scalars(
            select(ComputerWorkBlock).where(
                ComputerWorkBlock.status == "closed", ComputerWorkBlock.endAt < cutoff
            )
        )
    )
    runs = list(
        db.scalars(
            select(ComputerWorkBlockAnalysisRun).where(
                ComputerWorkBlockAnalysisRun.createdAt < cutoff
            )
        )
    )
    for row in runs:
        db.delete(row)
    for row in blocks:
        db.delete(row)
    db.commit()
    return len(blocks) + len(runs)
