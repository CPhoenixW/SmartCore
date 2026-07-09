from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.new_core.course_semester import sync_course_plans
from app.new_core.event_relations import mark_reminder_fired, sync_plan_reminders
from app.new_core.models import CourseEvt, CoursePlan, EvtBase, PlanEvt, RemindEvt, nowIso

_DEFAULT_TZ = ZoneInfo("Asia/Shanghai")
_REQUIRED_REMINDER_KINDS = {"plan_start_10m", "plan_end_10m"}


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_DEFAULT_TZ)
    return parsed.astimezone(_DEFAULT_TZ)


def _remove_nondefault_plan_reminders(db: Session) -> int:
    rows = db.scalars(
        select(RemindEvt).where(
            RemindEvt.planEvtId.is_not(None),
            RemindEvt.remindKind.not_in(_REQUIRED_REMINDER_KINDS),
        )
    ).all()
    removed = 0
    for reminder in rows:
        base = db.get(EvtBase, reminder.evtId)
        db.delete(reminder)
        if base is not None:
            db.delete(base)
        removed += 1
    if removed:
        db.flush()
    return removed


def ensure_missing_relations(db: Session) -> dict[str, int]:
    """Backfill required relations and remove obsolete plan reminder variants."""
    reminders = 0
    course_plans = 0
    removed_reminders = _remove_nondefault_plan_reminders(db)

    reminder_kinds: dict[str, set[str]] = defaultdict(set)
    for plan_id, kind in db.execute(
        select(RemindEvt.planEvtId, RemindEvt.remindKind).where(RemindEvt.planEvtId.is_not(None))
    ).all():
        reminder_kinds[str(plan_id)].add(str(kind))

    plan_ids = [str(value) for value in db.scalars(select(PlanEvt.evtId)).all()]
    for plan_id in plan_ids:
        missing = _REQUIRED_REMINDER_KINDS - reminder_kinds.get(plan_id, set())
        if missing:
            sync_plan_reminders(db, plan_id)
            reminders += len(missing)

    occurrence_counts = {
        str(course_id): int(count)
        for course_id, count in db.execute(
            select(CoursePlan.courseEvtId, func.count(CoursePlan.planEvtId))
            .group_by(CoursePlan.courseEvtId)
        ).all()
    }
    for course_id in [str(value) for value in db.scalars(select(CourseEvt.evtId)).all()]:
        if occurrence_counts.get(course_id, 0) == 0:
            course_plans += len(sync_course_plans(db, course_id))

    db.commit()
    return {
        "reminders": reminders,
        "removedPlanReminders": removed_reminders,
        "coursePlans": course_plans,
    }


def close_past_course_occurrences(db: Session, *, now: str | None = None) -> int:
    current = _parse(now) if now else datetime.now(_DEFAULT_TZ)
    changed = 0
    rows = db.execute(
        select(EvtBase, PlanEvt, CoursePlan)
        .join(PlanEvt, PlanEvt.evtId == EvtBase.evtId)
        .join(CoursePlan, CoursePlan.planEvtId == PlanEvt.evtId)
        .where(EvtBase.stat == "todo")
    ).all()
    for base, plan, _ in rows:
        end = _parse(plan.stTime) + timedelta(minutes=max(1, int(plan.durationMin)))
        if end >= current:
            continue
        base.stat = "done"
        base.updatedAt = nowIso()
        sync_plan_reminders(db, base.evtId)
        for reminder in db.scalars(
            select(RemindEvt).where(
                RemindEvt.planEvtId == base.evtId,
                RemindEvt.firedAt.is_(None),
            )
        ).all():
            mark_reminder_fired(db, reminder.evtId, fired_at=current.isoformat())
        changed += 1
    if changed:
        db.commit()
    return changed
