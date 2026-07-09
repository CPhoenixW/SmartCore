from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.new_core import crud
from app.new_core.event_relations import ensure_all_relations, mark_reminder_fired
from app.new_core.models import DdlEvt, EvtBase, RemindEvt
from app.new_core.notify import routeNotify

_DEFAULT_TZ = ZoneInfo("Asia/Shanghai")


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


def runReminderTick(
    db: Session,
    *,
    now: str,
    screenOnline: bool,
) -> dict[str, int]:
    nowDt = _parseNow(now)
    sent = 0

    # This also backfills relations for plans/courses created by older versions.
    ensure_all_relations(db)

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
        if not _isDue(reminder.triggerTime, nowDt):
            continue
        plan_base = db.get(EvtBase, reminder.planEvtId)
        if plan_base is None or plan_base.stat != "todo":
            reminder_base.stat = "cancelled"
            reminder_base.updatedAt = nowDt.isoformat()
            db.commit()
            continue
        dedup_key = f"remindEvt:{reminder_base.evtId}:{reminder.triggerTime}"
        if crud.notifyDedupExists(db, dedup_key):
            mark_reminder_fired(db, reminder_base.evtId, fired_at=nowDt.isoformat())
            db.commit()
            continue
        result = routeNotify(
            db,
            title=reminder_base.title,
            content=reminder_base.desc or plan_base.title,
            screenOnline=screenOnline,
            dedupKey=dedup_key,
            evtId=reminder.planEvtId,
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
