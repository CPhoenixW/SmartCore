from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.new_core.event_relations import (
    mark_reminder_fired,
    sync_course_plans,
    sync_plan_reminders,
)
from app.new_core.models import CourseEvt, CoursePlan, EvtBase, PlanEvt, RemindEvt, nowIso

_DEFAULT_TZ = ZoneInfo("Asia/Shanghai")
_REQUIRED_REMINDER_KINDS = {"plan_start_10m", "plan_end_10m"}


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_DEFAULT_TZ)
    return parsed.astimezone(_DEFAULT_TZ)


def ensure_missing_relations(db: Session) -> dict[str, int]:
    """Backfill legacy rows without rewriting already-customized occurrences."""
    reminders = 0
    course_plans = 0

    plan_ids = db.scalars(select(PlanEvt.evtId)).all()
    for plan_id in plan_ids:
        existing_kinds = set(
            db.scalars(
                select(RemindEvt.remindKind).where(RemindEvt.planEvtId == plan_id)
            ).all()
        )
        missing = _REQUIRED_REMINDER_KINDS - existing_kinds
        if missing:
            sync_plan_reminders(db, plan_id)
            reminders += len(missing)

    course_ids = db.scalars(select(CourseEvt.evtId)).all()
    for course_id in course_ids:
        count = db.scalar(
            select(func.count(CoursePlan.planEvtId)).where(CoursePlan.courseEvtId == course_id)
        ) or 0
        if int(count) == 0:
            course_plans += len(sync_course_plans(db, course_id))

    db.commit()
    return {"reminders": reminders, "coursePlans": course_plans}


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
