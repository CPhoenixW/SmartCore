from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.new_core import crud
from app.new_core.event_relations import mark_reminder_fired
from app.new_core.models import AppUser, DdlEvt, EvtBase, PlanEvt, RemindEvt
from app.new_core.notify import routeNotify
from app.new_core.relation_maintenance import (
    close_past_course_occurrences,
    ensure_missing_relations,
)

_DEFAULT_TZ = ZoneInfo("Asia/Shanghai")
_REMINDER_DELIVERY_WINDOW = timedelta(minutes=5)


def _parseNow(now: str) -> datetime:
    parsed = datetime.fromisoformat(now.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=_DEFAULT_TZ)
    return parsed.astimezone(_DEFAULT_TZ)


def _isDue(instant: str | None, now: datetime) -> bool:
    if not instant:
        return False
    due = _parseNow(instant)
    return due <= now


def _plan_reminder_copy(
    db: Session,
    reminder: RemindEvt,
    plan_base: EvtBase,
) -> tuple[str, str]:
    plan = db.get(PlanEvt, reminder.planEvtId)
    if plan is None:
        return plan_base.title, plan_base.desc or plan_base.title
    user = db.get(AppUser, plan_base.userId)
    english = bool(user and user.language == "en")
    start = _parseNow(plan.stTime)
    end = start + timedelta(minutes=max(1, int(plan.durationMin)))
    ending = reminder.remindKind == "plan_end_10m"
    target = end if ending else start
    if english:
        phase = "ends" if ending else "starts"
        return (
            f"{plan_base.title} · 10 min before it {phase}",
            f"The plan {phase} in 10 minutes: {target.isoformat()}",
        )
    phase = "结束" if ending else "开始"
    return (
        f"{plan_base.title} · {phase}前 10 分钟",
        f"计划将在 10 分钟后{phase}：{target.isoformat()}",
    )


def runReminderTick(
    db: Session,
    *,
    now: str,
    screenOnline: bool,
) -> dict[str, int]:
    nowDt = _parseNow(now)
    sent = 0

    ensure_missing_relations(db)
    close_past_course_occurrences(db, now=nowDt.isoformat())

    reminder_rows = db.execute(
        select(EvtBase, RemindEvt)
        .join(RemindEvt, RemindEvt.evtId == EvtBase.evtId)
        .where(
            EvtBase.stat == "todo",
            EvtBase.evtType == "remind",
            RemindEvt.firedAt.is_(None),
        )
        .order_by(RemindEvt.triggerTime.asc())
    ).all()
    for reminder_base, reminder in reminder_rows:
        trigger = _parseNow(reminder.triggerTime)
        if trigger > nowDt:
            continue

        target_evt_id = reminder_base.evtId
        title = reminder_base.title
        content = reminder_base.desc or reminder_base.title
        if reminder.planEvtId is not None:
            plan_base = db.get(EvtBase, reminder.planEvtId)
            if plan_base is None or plan_base.stat != "todo":
                reminder_base.stat = "cancelled"
                reminder_base.updatedAt = nowDt.isoformat()
                db.commit()
                continue
            target_evt_id = reminder.planEvtId
            title, content = _plan_reminder_copy(db, reminder, plan_base)

        if nowDt - trigger > _REMINDER_DELIVERY_WINDOW:
            mark_reminder_fired(db, reminder_base.evtId, fired_at=nowDt.isoformat())
            db.commit()
            continue
        dedup_key = f"remindEvt:{reminder_base.evtId}:{reminder.triggerTime}"
        if crud.notifyDedupExists(db, dedup_key):
            mark_reminder_fired(db, reminder_base.evtId, fired_at=nowDt.isoformat())
            db.commit()
            continue
        result = routeNotify(
            db,
            title=title,
            content=content,
            screenOnline=screenOnline,
            dedupKey=dedup_key,
            evtId=target_evt_id,
            phase="notice",
        )
        if result.get("stat") in {"sent", "deduped"}:
            mark_reminder_fired(db, reminder_base.evtId, fired_at=nowDt.isoformat())
            db.commit()
            sent += 1

    ddl_rows = db.execute(
        select(EvtBase, DdlEvt)
        .join(DdlEvt, DdlEvt.evtId == EvtBase.evtId)
        .where(EvtBase.stat == "todo", EvtBase.evtType == "ddl")
    ).all()
    for base, ddl in ddl_rows:
        if not _isDue(ddl.endTime, nowDt):
            continue
        dedup_key = f"ddlDue:{base.evtId}:{ddl.endTime}"
        if crud.notifyDedupExists(db, dedup_key):
            continue
        result = routeNotify(
            db,
            title=base.title,
            content=ddl.endTime or base.title,
            screenOnline=screenOnline,
            dedupKey=dedup_key,
            evtId=base.evtId,
            phase="end",
        )
        if result.get("stat") in {"sent", "deduped"}:
            sent += 1

    return {"sent": sent}
