from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.new_core import crud
from app.new_core.models import DdlEvt, EvtBase, PlanEvt
from app.new_core.notify import routeNotify

_DEFAULT_TZ = ZoneInfo("Asia/Shanghai")


def _parseNow(now: str) -> datetime:
    parsed = datetime.fromisoformat(now)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=_DEFAULT_TZ)
    return parsed


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

    planRows = db.execute(
        select(EvtBase, PlanEvt)
        .join(PlanEvt, PlanEvt.evtId == EvtBase.evtId)
        .where(EvtBase.stat == "todo", EvtBase.evtType == "plan")
    ).all()
    for base, plan in planRows:
        if not _isDue(plan.stTime, nowDt):
            continue
        dedupKey = f"planDue:{base.evtId}:{plan.stTime}"
        if crud.notifyDedupExists(db, dedupKey):
            continue
        routeNotify(
            db,
            title=base.title,
            content=plan.stTime or base.title,
            screenOnline=screenOnline,
            dedupKey=dedupKey,
            evtId=base.evtId,
        )
        sent += 1

    ddlRows = db.execute(
        select(EvtBase, DdlEvt)
        .join(DdlEvt, DdlEvt.evtId == EvtBase.evtId)
        .where(EvtBase.stat == "todo", EvtBase.evtType == "ddl")
    ).all()
    for base, ddl in ddlRows:
        if not _isDue(ddl.endTime, nowDt):
            continue
        dedupKey = f"ddlDue:{base.evtId}:{ddl.endTime}"
        if crud.notifyDedupExists(db, dedupKey):
            continue
        routeNotify(
            db,
            title=base.title,
            content=ddl.endTime or base.title,
            screenOnline=screenOnline,
            dedupKey=dedupKey,
            evtId=base.evtId,
        )
        sent += 1

    return {"sent": sent}
