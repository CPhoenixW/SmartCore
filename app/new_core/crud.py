from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.new_core.models import (
    ActLog,
    AppUser,
    CourseEvt,
    DdlEvt,
    DdlPlan,
    Device,
    DeviceStateLog,
    EvtBase,
    Idea,
    MsgLog,
    NotifyLog,
    PlanEvt,
    newId,
    nowIso,
)

_DEFAULT_TZ = ZoneInfo("Asia/Shanghai")
DEFAULT_USER_ID = "default"


def _parseNow(now: str) -> datetime:
    parsed = datetime.fromisoformat(now)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=_DEFAULT_TZ)
    return parsed


def _ensure_user(db: Session, userId: str = DEFAULT_USER_ID) -> AppUser:
    user = db.get(AppUser, userId)
    if user is None:
        user = AppUser(userId=userId, displayName="默认用户")
        db.add(user)
        db.flush()
    return user


def _evtDict(base: EvtBase, **extra: Any) -> dict[str, Any]:
    data = {
        "evtId": base.evtId,
        "userId": base.userId,
        "title": base.title,
        "desc": base.desc,
        "evtType": base.evtType,
        "prio": base.prio,
        "stat": base.stat,
        "createdAt": base.createdAt,
        "updatedAt": base.updatedAt,
    }
    data.update(extra)
    return data


def _planDict(base: EvtBase, plan: PlanEvt) -> dict[str, Any]:
    return _evtDict(base, stTime=plan.stTime, durationMin=plan.durationMin, dueAt=plan.stTime)


def _ddl_links(db: Session, ddlEvtId: str) -> list[dict[str, Any]]:
    links = db.scalars(
        select(DdlPlan).where(DdlPlan.ddlEvtId == ddlEvtId).order_by(DdlPlan.sortOrder.asc())
    ).all()
    result: list[dict[str, Any]] = []
    for link in links:
        base = db.get(EvtBase, link.planEvtId)
        plan = db.get(PlanEvt, link.planEvtId)
        if base and plan:
            item = _planDict(base, plan)
            item.update({"planRole": link.planRole, "sortOrder": link.sortOrder})
            result.append(item)
    return result


def _ddlDict(db: Session, base: EvtBase, ddl: DdlEvt) -> dict[str, Any]:
    return _evtDict(
        base,
        endTime=ddl.endTime,
        ddlAt=ddl.endTime,
        hardDdl=ddl.hardDdl,
        plans=_ddl_links(db, base.evtId),
    )


def _courseDict(base: EvtBase, course: CourseEvt) -> dict[str, Any]:
    return _evtDict(
        base,
        courseName=course.courseName,
        teacher=course.teacher,
        location=course.location,
        room=course.location,
        stTime=course.stTime,
        startTime=course.stTime,
        endTime=course.endTime,
        stDate=course.stDate,
        endDate=course.endDate,
        classDate=course.stDate,
        weekDay=course.weekDay,
        weekday=course.weekDay,
        startWeek=course.startWeek,
        endWeek=course.endWeek,
        weekMode=course.weekMode,
        tplId=course.evtId,
        attendStat="unknown",
    )


def _ideaDict(idea: Idea) -> dict[str, Any]:
    return {
        "ideaId": idea.ideaId,
        "userId": idea.userId,
        "content": idea.content,
        "srcType": idea.srcType,
        "mediaPath": idea.mediaPath,
        "handled": idea.handled,
        "createdAt": idea.createdAt,
    }


def _devStateDict(row: DeviceStateLog) -> dict[str, Any]:
    return {
        "stateId": row.stateLogId,
        "stateLogId": row.stateLogId,
        "devId": row.deviceId,
        "deviceId": row.deviceId,
        "state": row.state,
        "confidence": row.confidence,
        "seenAt": row.seenAt,
        "meta": row.meta,
    }


def _notifyLogDict(row: NotifyLog) -> dict[str, Any]:
    return {
        "notifyId": row.notifyId,
        "userId": row.userId,
        "evtId": row.evtId,
        "channel": row.channel,
        "receiver": row.receiver,
        "sourceDeviceId": row.sourceDeviceId,
        "routeReason": row.routeReason,
        "title": row.title,
        "content": row.content,
        "scheduledAt": row.scheduledAt,
        "sentAt": row.sentAt,
        "stat": row.stat,
        "failReason": row.failReason,
        "dedupKey": row.dedupKey,
    }


def _msgLogDict(row: MsgLog) -> dict[str, Any]:
    return {
        "msgId": row.msgId,
        "userId": row.userId,
        "channel": row.channel,
        "src": row.channel,
        "direction": row.direction,
        "externalId": row.externalId,
        "sourceDeviceId": row.sourceDeviceId,
        "rawText": row.rawText,
        "intent": row.intent,
        "stat": row.stat,
        "createdAt": row.createdAt,
    }


def _actLogDict(row: ActLog) -> dict[str, Any]:
    return {
        "actId": row.actId,
        "userId": row.userId,
        "actorKind": row.actorKind,
        "src": row.actorKind,
        "actorId": row.actorId,
        "actor": row.actorId,
        "action": row.action,
        "actType": row.action,
        "targetKind": row.targetKind,
        "targetId": row.targetId,
        "sourceDeviceId": row.sourceDeviceId,
        "result": row.result,
        "errorMessage": row.errorMessage,
        "createdAt": row.createdAt,
    }


def _recordAct(
    db: Session,
    *,
    userId: str = DEFAULT_USER_ID,
    actorKind: str | None = None,
    actorId: str | None = None,
    action: str | None = None,
    targetKind: str | None = None,
    targetId: str | None = None,
    sourceDeviceId: str | None = None,
    result: str = "ok",
    errorMessage: str | None = None,
    src: str | None = None,
    actType: str | None = None,
    beforeData: dict | None = None,
    afterData: dict | None = None,
    undoToken: str | None = None,
) -> ActLog:
    _ensure_user(db, userId)
    row = ActLog(
        userId=userId,
        actorKind=actorKind or src or "user",
        actorId=actorId,
        action=action or actType or "update",
        targetKind=targetKind or "evt",
        targetId=targetId or "",
        sourceDeviceId=sourceDeviceId,
        result=result,
        errorMessage=errorMessage,
    )
    db.add(row)
    return row


def _base_event(
    *,
    userId: str,
    title: str,
    evtType: str,
    desc: str | None,
    prio: str,
    stat: str = "todo",
) -> EvtBase:
    now = nowIso()
    return EvtBase(
        evtId=newId(),
        userId=userId,
        title=title,
        desc=desc,
        evtType=evtType,
        prio=prio,
        stat=stat,
        createdAt=now,
        updatedAt=now,
    )


def createPlanEvt(
    db: Session,
    *,
    title: str,
    stTime: str,
    durationMin: int = 30,
    src: str = "api",
    desc: str | None = None,
    prio: str = "mid",
    userId: str = DEFAULT_USER_ID,
) -> dict[str, Any]:
    _ensure_user(db, userId)
    base = _base_event(userId=userId, title=title, evtType="plan", desc=desc, prio=prio)
    db.add(base)
    db.flush()
    plan = PlanEvt(evtId=base.evtId, stTime=stTime, durationMin=durationMin)
    db.add(plan)
    result = _planDict(base, plan)
    _recordAct(db, userId=userId, src=src, action="create", targetKind="planEvt", targetId=base.evtId)
    db.commit()
    return result


def createLifeEvt(
    db: Session,
    *,
    title: str,
    dueAt: str | None,
    src: str,
    desc: str | None = None,
    prio: str = "mid",
) -> dict[str, Any]:
    return createPlanEvt(db, title=title, stTime=dueAt or nowIso(), durationMin=30, src=src, desc=desc, prio=prio)


def _create_linked_plan(
    db: Session,
    *,
    userId: str,
    ddlEvtId: str,
    title: str,
    stTime: str,
    durationMin: int,
    planRole: str,
    sortOrder: int,
    prio: str,
) -> None:
    base = _base_event(userId=userId, title=title, evtType="plan", desc="DDL 自动生成计划", prio=prio)
    db.add(base)
    db.flush()
    db.add(PlanEvt(evtId=base.evtId, stTime=stTime, durationMin=durationMin))
    db.add(DdlPlan(ddlEvtId=ddlEvtId, planEvtId=base.evtId, planRole=planRole, sortOrder=sortOrder))
    _recordAct(db, userId=userId, actorKind="system", action="auto_create", targetKind="planEvt", targetId=base.evtId)


def createDdlEvt(
    db: Session,
    *,
    title: str,
    endTime: str | None = None,
    ddlAt: str | None = None,
    hardDdl: bool = False,
    src: str = "api",
    desc: str | None = None,
    prio: str = "high",
    userId: str = DEFAULT_USER_ID,
) -> dict[str, Any]:
    finalEndTime = endTime or ddlAt
    if not finalEndTime:
        raise ValueError("endTime is required for ddlEvt")
    _ensure_user(db, userId)
    base = _base_event(userId=userId, title=title, evtType="ddl", desc=desc, prio=prio)
    db.add(base)
    db.flush()
    ddl = DdlEvt(evtId=base.evtId, endTime=finalEndTime, hardDdl=hardDdl)
    db.add(ddl)
    _recordAct(db, userId=userId, src=src, action="create", targetKind="ddlEvt", targetId=base.evtId)
    try:
        end_dt = _parseNow(finalEndTime)
        defaults = [
            ("one_day_before", end_dt - timedelta(days=1)),
            ("one_hour_before", end_dt - timedelta(hours=1)),
        ]
        for order, (role, st_dt) in enumerate(defaults):
            _create_linked_plan(
                db,
                userId=userId,
                ddlEvtId=base.evtId,
                title=f"{title} · {'提前一天' if role == 'one_day_before' else '提前一小时'}",
                stTime=st_dt.isoformat(),
                durationMin=30,
                planRole=role,
                sortOrder=order,
                prio=prio,
            )
    except ValueError:
        pass
    db.commit()
    return _ddlDict(db, base, ddl)


def createCourseEvt(
    db: Session,
    *,
    courseName: str,
    title: str | None = None,
    teacher: str | None = None,
    location: str | None = None,
    room: str | None = None,
    stTime: str | None = None,
    startTime: str | None = None,
    endTime: str | None = None,
    stDate: str | None = None,
    endDate: str | None = None,
    weekDay: int | None = None,
    weekday: int | None = None,
    startWeek: int | None = None,
    endWeek: int | None = None,
    weekMode: str = "all",
    desc: str | None = None,
    prio: str = "mid",
    src: str = "api",
    userId: str = DEFAULT_USER_ID,
    **_: Any,
) -> dict[str, Any]:
    final_st = stTime or startTime
    final_weekday = weekDay if weekDay is not None else weekday
    final_location = location or room
    if not final_st or not endTime or not stDate or not endDate or final_weekday is None:
        raise ValueError("courseEvt requires stTime, endTime, stDate, endDate and weekDay")
    _ensure_user(db, userId)
    base = _base_event(userId=userId, title=title or courseName, evtType="course", desc=desc, prio=prio)
    db.add(base)
    db.flush()
    course = CourseEvt(
        evtId=base.evtId,
        courseName=courseName,
        teacher=teacher,
        location=final_location,
        stTime=final_st,
        endTime=endTime,
        stDate=stDate,
        endDate=endDate,
        weekDay=final_weekday,
        startWeek=startWeek,
        endWeek=endWeek,
        weekMode=weekMode,
    )
    db.add(course)
    _recordAct(db, userId=userId, src=src, action="create", targetKind="courseEvt", targetId=base.evtId)
    db.commit()
    return _courseDict(base, course)


def createCourseTpl(db: Session, **fields: Any) -> dict[str, Any]:
    courseName = fields.pop("courseName")
    return createCourseEvt(db, courseName=courseName, **fields)


def createCourseInst(
    db: Session,
    *,
    title: str,
    tplId: str | None = None,
    classDate: str | None,
    attendStat: str = "unknown",
    src: str = "api",
) -> dict[str, Any]:
    return createCourseEvt(
        db,
        title=title,
        courseName=title,
        stTime="08:00",
        endTime="08:45",
        stDate=classDate or datetime.now(_DEFAULT_TZ).date().isoformat(),
        endDate=classDate or datetime.now(_DEFAULT_TZ).date().isoformat(),
        weekDay=datetime.now(_DEFAULT_TZ).isoweekday(),
        src=src,
    )


def createIdea(
    db: Session,
    *,
    content: str,
    srcType: str = "text",
    mediaPath: str | None = None,
    userId: str = DEFAULT_USER_ID,
) -> dict[str, Any]:
    _ensure_user(db, userId)
    idea = Idea(userId=userId, content=content, srcType=srcType, mediaPath=mediaPath)
    db.add(idea)
    db.flush()
    result = _ideaDict(idea)
    _recordAct(db, userId=userId, src="api", action="create", targetKind="idea", targetId=idea.ideaId)
    db.commit()
    return result


def ideaToLifeEvt(db: Session, *, ideaId: str, title: str, dueAt: str | None, src: str) -> dict[str, Any]:
    raise ValueError("idea no longer converts to event")


def listEvt(db: Session, *, userId: str = DEFAULT_USER_ID) -> list[dict[str, Any]]:
    rows = db.scalars(select(EvtBase).where(EvtBase.userId == userId).order_by(EvtBase.createdAt.asc())).all()
    results: list[dict[str, Any]] = []
    for base in rows:
        if base.evtType == "plan":
            plan = db.get(PlanEvt, base.evtId)
            if plan:
                results.append(_planDict(base, plan))
        elif base.evtType == "ddl":
            ddl = db.get(DdlEvt, base.evtId)
            if ddl:
                results.append(_ddlDict(db, base, ddl))
        elif base.evtType == "course":
            course = db.get(CourseEvt, base.evtId)
            if course:
                results.append(_courseDict(base, course))
    return results


def listPlanEvt(db: Session) -> list[dict[str, Any]]:
    return [item for item in listEvt(db) if item["evtType"] == "plan"]


def listLifeEvt(db: Session) -> list[dict[str, Any]]:
    return listPlanEvt(db)


def listDdlEvt(db: Session) -> list[dict[str, Any]]:
    return [item for item in listEvt(db) if item["evtType"] == "ddl"]


def listCourseEvt(db: Session) -> list[dict[str, Any]]:
    return [item for item in listEvt(db) if item["evtType"] == "course"]


def listCourseInst(db: Session) -> list[dict[str, Any]]:
    return listCourseEvt(db)


def listCourseTpl(db: Session) -> list[dict[str, Any]]:
    return listCourseEvt(db)


def listIdeas(db: Session, *, userId: str = DEFAULT_USER_ID) -> list[dict[str, Any]]:
    rows = db.scalars(select(Idea).where(Idea.userId == userId).order_by(Idea.createdAt.asc())).all()
    return [_ideaDict(row) for row in rows]


def listDevState(db: Session) -> list[dict[str, Any]]:
    rows = db.scalars(select(DeviceStateLog).order_by(DeviceStateLog.seenAt.desc())).all()
    return [_devStateDict(row) for row in rows]


def listNotifyLog(db: Session) -> list[dict[str, Any]]:
    rows = db.scalars(select(NotifyLog).order_by(NotifyLog.scheduledAt.asc())).all()
    return [_notifyLogDict(row) for row in rows]


def listMsgLog(db: Session) -> list[dict[str, Any]]:
    rows = db.scalars(select(MsgLog).order_by(MsgLog.createdAt.asc())).all()
    return [_msgLogDict(row) for row in rows]


def listActLog(db: Session) -> list[dict[str, Any]]:
    rows = db.scalars(select(ActLog).order_by(ActLog.createdAt.asc())).all()
    return [_actLogDict(row) for row in rows]


def getLatestDevState(db: Session, *, devId: str = "pi") -> dict[str, Any] | None:
    row = db.scalars(
        select(DeviceStateLog)
        .where(DeviceStateLog.deviceId == devId)
        .order_by(DeviceStateLog.seenAt.desc())
        .limit(1)
    ).first()
    return _devStateDict(row) if row else None


def upsertDevState(
    db: Session,
    *,
    devId: str,
    state: str,
    confidence: float | None = None,
    seenAt: str | None = None,
    meta: dict | None = None,
) -> dict[str, Any]:
    _ensure_user(db)
    device = db.get(Device, devId)
    if device is None:
        device = Device(deviceId=devId, userId=DEFAULT_USER_ID, deviceName=devId, deviceKind="screen")
        db.add(device)
        db.flush()
    row = DeviceStateLog(deviceId=devId, state=state, confidence=confidence, seenAt=seenAt or nowIso(), meta=meta)
    db.add(row)
    _recordAct(db, actorKind="device", action="update", targetKind="device", targetId=devId)
    db.commit()
    db.refresh(row)
    return _devStateDict(row)


def updateEvt(db: Session, evtId: str, **fields: Any) -> dict[str, Any]:
    base = db.get(EvtBase, evtId)
    if base is None:
        raise ValueError(f"evt not found: {evtId}")
    for key in ("title", "desc", "prio", "stat"):
        if key in fields and fields[key] is not None:
            setattr(base, key, fields[key])
    if base.evtType == "plan":
        plan = db.get(PlanEvt, evtId)
        if plan is not None:
            if "stTime" in fields and fields["stTime"] is not None:
                plan.stTime = fields["stTime"]
            if "dueAt" in fields and fields["dueAt"] is not None:
                plan.stTime = fields["dueAt"]
            if "durationMin" in fields and fields["durationMin"] is not None:
                plan.durationMin = int(fields["durationMin"])
    elif base.evtType == "ddl":
        ddl = db.get(DdlEvt, evtId)
        if ddl is not None:
            if "endTime" in fields and fields["endTime"] is not None:
                ddl.endTime = fields["endTime"]
            if "ddlAt" in fields and fields["ddlAt"] is not None:
                ddl.endTime = fields["ddlAt"]
            if "hardDdl" in fields and fields["hardDdl"] is not None:
                ddl.hardDdl = bool(fields["hardDdl"])
    elif base.evtType == "course":
        course = db.get(CourseEvt, evtId)
        if course is not None:
            mapping = {
                "courseName": "courseName",
                "teacher": "teacher",
                "location": "location",
                "room": "location",
                "stTime": "stTime",
                "startTime": "stTime",
                "endTime": "endTime",
                "stDate": "stDate",
                "classDate": "stDate",
                "endDate": "endDate",
                "weekDay": "weekDay",
                "weekday": "weekDay",
                "startWeek": "startWeek",
                "endWeek": "endWeek",
                "weekMode": "weekMode",
            }
            for key, attr in mapping.items():
                if key in fields and fields[key] is not None:
                    setattr(course, attr, fields[key])
    base.updatedAt = nowIso()
    _recordAct(db, userId=base.userId, src="api", action="update", targetKind="evt", targetId=evtId)
    db.commit()
    return next(item for item in listEvt(db, userId=base.userId) if item["evtId"] == evtId)


def cancelEvt(db: Session, evtId: str, *, src: str = "api") -> dict[str, Any]:
    base = db.get(EvtBase, evtId)
    if base is None:
        raise ValueError(f"evt not found: {evtId}")
    base.stat = "cancelled"
    base.updatedAt = nowIso()
    _recordAct(db, userId=base.userId, src=src, action="cancel", targetKind="evt", targetId=evtId)
    db.commit()
    return next(item for item in listEvt(db, userId=base.userId) if item["evtId"] == evtId)


def notifyDedupExists(db: Session, dedupKey: str) -> bool:
    return db.scalars(select(NotifyLog).where(NotifyLog.dedupKey == dedupKey)).first() is not None


def writeNotifyLog(
    db: Session,
    *,
    dedupKey: str | None,
    channel: str,
    title: str,
    content: str,
    stat: str,
    targetId: str | None = None,
    failReason: str | None = None,
) -> dict[str, Any]:
    _ensure_user(db)
    row = NotifyLog(
        userId=DEFAULT_USER_ID,
        evtId=targetId,
        channel=channel,
        title=title,
        content=content,
        scheduledAt=nowIso(),
        sentAt=nowIso(),
        stat=stat,
        failReason=failReason,
        dedupKey=dedupKey,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _notifyLogDict(row)


def createMsgLog(
    db: Session,
    *,
    src: str,
    externalId: str | None,
    rawText: str | None,
    intent: str | None,
    stat: str,
) -> dict[str, Any]:
    _ensure_user(db)
    row = MsgLog(
        userId=DEFAULT_USER_ID,
        channel=src,
        direction="in",
        externalId=externalId,
        rawText=rawText,
        intent=intent,
        stat=stat,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _msgLogDict(row)


def msgLogExists(db: Session, *, src: str, externalId: str) -> bool:
    return db.scalars(select(MsgLog).where(MsgLog.channel == src, MsgLog.externalId == externalId)).first() is not None


def applyReminderAction(db: Session, *, evtId: str, action: str, now: str, src: str) -> dict[str, Any]:
    base = db.get(EvtBase, evtId)
    if base is None:
        raise ValueError(f"evt not found: {evtId}")
    if action == "done":
        return updateEvt(db, evtId, stat="done")
    if action == "snooze10":
        newInstant = (_parseNow(now) + timedelta(minutes=10)).isoformat()
        if base.evtType == "plan":
            return updateEvt(db, evtId, stTime=newInstant)
        if base.evtType == "ddl":
            return updateEvt(db, evtId, endTime=newInstant)
        raise ValueError(f"snooze not supported for evtType: {base.evtType}")
    raise ValueError(f"unknown reminder action: {action}")


def undoByToken(db: Session, undoToken: str) -> dict[str, Any]:
    raise ValueError("undo is disabled in the simplified serial schema")


def sendReminder(db: Session, **kwargs: Any) -> dict[str, Any]:
    from app.new_core.notify import sendReminder as _sendReminder

    return _sendReminder(db, **kwargs)
