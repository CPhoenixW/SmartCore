from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.new_core import crud
from app.new_core.models import DdlEvt, EvtBase, LifeEvt
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

    lifeRows = db.execute(
        select(EvtBase, LifeEvt)
        .join(LifeEvt, LifeEvt.evtId == EvtBase.evtId)
        .where(EvtBase.stat == "todo", EvtBase.evtType == "life")
    ).all()
    for base, life in lifeRows:
        if not _isDue(life.dueAt, nowDt):
            continue
        dedupKey = f"lifeDue:{base.evtId}"
        if crud.notifyDedupExists(db, dedupKey):
            continue
        routeNotify(
            db,
            title=base.title,
            content=life.dueAt or base.title,
            screenOnline=screenOnline,
            dedupKey=dedupKey,
        )
        sent += 1

    ddlRows = db.execute(
        select(EvtBase, DdlEvt)
        .join(DdlEvt, DdlEvt.evtId == EvtBase.evtId)
        .where(EvtBase.stat == "todo", EvtBase.evtType == "ddl")
    ).all()
    for base, ddl in ddlRows:
        if not _isDue(ddl.ddlAt, nowDt):
            continue
        dedupKey = f"ddlDue:{base.evtId}"
        if crud.notifyDedupExists(db, dedupKey):
            continue
        routeNotify(
            db,
            title=base.title,
            content=ddl.ddlAt or base.title,
            screenOnline=screenOnline,
            dedupKey=dedupKey,
        )
        sent += 1

    return {"sent": sent}
