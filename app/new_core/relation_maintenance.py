from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.new_core.event_relations import mark_reminder_fired, sync_plan_reminders
from app.new_core.models import CoursePlan, EvtBase, PlanEvt, RemindEvt, nowIso

_DEFAULT_TZ = ZoneInfo("Asia/Shanghai")


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_DEFAULT_TZ)
    return parsed.astimezone(_DEFAULT_TZ)


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
