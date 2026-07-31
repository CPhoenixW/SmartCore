from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.server.new_core.event_relations import get_event, update_event
from app.server.new_core.models import DailySummary, EvtBase, newId, nowIso

_SUMMARY_STATS = {"queued", "complete", "failed"}
_MAX_COMPLETION_SUMMARY_LENGTH = 4000
_MAX_DAILY_SUMMARY_CONTENT_LENGTH = 20000


def _report_date(value: str) -> str:
    try:
        return date.fromisoformat(str(value).strip()).isoformat()
    except ValueError as exc:
        raise ValueError("reportDate must be YYYY-MM-DD") from exc


def daily_summary_dict(row: DailySummary) -> dict[str, Any]:
    return {
        "summaryId": row.summaryId,
        "reportDate": row.reportDate,
        "content": row.content,
        "stat": row.stat,
        "generatedAt": row.generatedAt,
        "createdAt": row.createdAt,
        "updatedAt": row.updatedAt,
    }


def list_daily_summaries(
    db: Session,
    *,
    user_id: str,
    report_date: str | None = None,
    text: str | None = None,
) -> list[dict[str, Any]]:
    query = select(DailySummary).where(DailySummary.userId == user_id)
    if report_date:
        query = query.where(DailySummary.reportDate == _report_date(report_date))
    rows = db.scalars(query.order_by(DailySummary.reportDate.desc())).all()
    needle = str(text or "").strip().lower()
    if needle:
        rows = [
            row
            for row in rows
            if needle in row.reportDate.lower() or needle in str(row.content or "").lower()
        ]
    return [daily_summary_dict(row) for row in rows]


def queue_daily_summary(
    db: Session,
    *,
    user_id: str,
    report_date: str,
) -> tuple[DailySummary, bool]:
    normalized_date = _report_date(report_date)
    existing = db.scalar(
        select(DailySummary).where(
            DailySummary.userId == user_id,
            DailySummary.reportDate == normalized_date,
        )
    )
    if existing is not None and existing.stat in {"queued", "complete"}:
        return existing, False
    now = nowIso()
    if existing is None:
        existing = DailySummary(
            summaryId=newId(),
            userId=user_id,
            reportDate=normalized_date,
            stat="queued",
            createdAt=now,
            updatedAt=now,
        )
        db.add(existing)
    else:
        existing.content = None
        existing.stat = "queued"
        existing.errorMessage = None
        existing.generatedAt = None
        existing.updatedAt = now
    db.commit()
    db.refresh(existing)
    return existing, True


def store_daily_summary(
    db: Session,
    *,
    user_id: str,
    report_date: str,
    stat: str,
    content: str | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    normalized_stat = str(stat).strip().lower()
    if normalized_stat not in _SUMMARY_STATS:
        raise ValueError("stat must be queued, complete, or failed")
    normalized_date = _report_date(report_date)
    clean_content = str(content or "").strip() or None
    if normalized_stat == "complete" and not clean_content:
        raise ValueError("content is required for a complete daily summary")
    row = db.scalar(
        select(DailySummary).where(
            DailySummary.userId == user_id,
            DailySummary.reportDate == normalized_date,
        )
    )
    now = nowIso()
    if row is None:
        row = DailySummary(
            summaryId=newId(),
            userId=user_id,
            reportDate=normalized_date,
            createdAt=now,
        )
        db.add(row)
    row.content = clean_content if normalized_stat == "complete" else None
    row.stat = normalized_stat
    row.errorMessage = str(error_message or "").strip()[:1000] or None
    row.generatedAt = now if normalized_stat == "complete" else None
    row.updatedAt = now
    db.commit()
    db.refresh(row)
    return daily_summary_dict(row)


def update_daily_summary_content(
    db: Session,
    *,
    user_id: str,
    summary_id: str,
    content: str,
    expected_updated_at: str | None = None,
) -> dict[str, Any]:
    row = db.scalar(
        select(DailySummary).where(
            DailySummary.summaryId == summary_id,
            DailySummary.userId == user_id,
        )
    )
    if row is None:
        raise ValueError("daily summary not found")
    if expected_updated_at is not None and row.updatedAt != expected_updated_at:
        raise ValueError("stale daily summary")
    clean_content = str(content or "").strip()
    if not clean_content:
        raise ValueError("content is required")
    if len(clean_content) > _MAX_DAILY_SUMMARY_CONTENT_LENGTH:
        raise ValueError("content must not exceed 20000 characters")
    row.content = clean_content
    row.stat = "complete"
    row.errorMessage = None
    row.updatedAt = nowIso()
    db.commit()
    db.refresh(row)
    return daily_summary_dict(row)


def complete_event_with_summary(
    db: Session,
    *,
    user_id: str,
    event_id: str,
    summary: str,
    src: str = "openclaw",
) -> dict[str, Any]:
    base = db.get(EvtBase, event_id)
    if base is None or base.userId != user_id:
        raise ValueError(f"evt not found: {event_id}")
    if base.evtType == "remind":
        raise ValueError("reminder events cannot store completion summaries")
    clean_summary = str(summary or "").strip()
    if not clean_summary:
        raise ValueError("summary required")
    if len(clean_summary) > _MAX_COMPLETION_SUMMARY_LENGTH:
        raise ValueError("summary must not exceed 4000 characters")
    note = f"完成总结：{clean_summary}"
    existing = str(base.desc or "").strip()
    notes = [part.strip() for part in existing.split("\n\n") if part.strip()]
    if note in notes and base.stat == "done":
        return get_event(db, event_id)
    description = "\n\n".join([*notes, note])
    return update_event(
        db,
        event_id,
        src=src,
        desc=description,
        stat="done",
    )
