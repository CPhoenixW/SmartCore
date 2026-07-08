from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.new_core import crud
from app.new_core.models import DdlEvt, EvtBase, PlanEvt
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

    planRows = db.execute(
        select(EvtBase, PlanEvt)
        .join(PlanEvt, PlanEvt.evtId == EvtBase.evtId)
        .where(EvtBase.stat == "todo", EvtBase.evtType == "plan")
    ).all()
    for base, plan in planRows:
        start = _parseNow(plan.stTime)
        end = start + timedelta(minutes=max(1, int(plan.durationMin or 0)))

        start_key = f"planStart:{base.evtId}:{plan.stTime}"
        if start <= nowDt < end and not crud.notifyDedupExists(db, start_key):
            routeNotify(
                db,
                title=base.title,
                content=f"计划已开始：{plan.stTime}",
                screenOnline=screenOnline,
                dedupKey=start_key,
                evtId=base.evtId,
                phase="start",
            )
            sent += 1

        end_key = f"planEnd:{base.evtId}:{end.isoformat()}"
        if nowDt >= end and not crud.notifyDedupExists(db, end_key):
            routeNotify(
                db,
                title=base.title,
                content=f"计划时间已结束：{end.isoformat()}",
                screenOnline=screenOnline,
                dedupKey=end_key,
                evtId=base.evtId,
                phase="end",
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
            phase="end",
        )
        sent += 1

    return {"sent": sent}
