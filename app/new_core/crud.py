from __future__ import annotations

import secrets
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.new_core.models import (
    ActLog,
    CourseInst,
    CourseTpl,
    DdlEvt,
    DevState,
    EvtBase,
    Idea,
    IdeaToEvt,
    LifeEvt,
    MsgLog,
    NotifyLog,
    newId,
    nowIso,
)


def _evtDict(base: EvtBase, **extra: Any) -> dict[str, Any]:
    data = {
        "evtId": base.evtId,
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


def _lifeDict(base: EvtBase, life: LifeEvt) -> dict[str, Any]:
    return _evtDict(base, dueAt=life.dueAt, doneAt=life.doneAt)


def _ddlDict(base: EvtBase, ddl: DdlEvt) -> dict[str, Any]:
    return _evtDict(base, ddlAt=ddl.ddlAt, hardDdl=ddl.hardDdl)


def _courseInstDict(base: EvtBase, inst: CourseInst) -> dict[str, Any]:
    return _evtDict(
        base,
        tplId=inst.tplId,
        classDate=inst.classDate,
        attendStat=inst.attendStat,
    )


def _courseTplDict(tpl: CourseTpl) -> dict[str, Any]:
    return {
        "tplId": tpl.tplId,
        "courseName": tpl.courseName,
        "teacher": tpl.teacher,
        "room": tpl.room,
        "weekday": tpl.weekday,
        "startTime": tpl.startTime,
        "endTime": tpl.endTime,
        "startWeek": tpl.startWeek,
        "endWeek": tpl.endWeek,
        "weekMode": tpl.weekMode,
        "semester": tpl.semester,
    }


def _ideaDict(idea: Idea) -> dict[str, Any]:
    return {
        "ideaId": idea.ideaId,
        "content": idea.content,
        "srcType": idea.srcType,
        "mediaPath": idea.mediaPath,
        "handled": idea.handled,
        "createdAt": idea.createdAt,
    }


def _devStateDict(state: DevState) -> dict[str, Any]:
    return {
        "stateId": state.stateId,
        "devId": state.devId,
        "state": state.state,
        "confidence": state.confidence,
        "seenAt": state.seenAt,
        "meta": state.meta,
    }


def _notifyLogDict(row: NotifyLog) -> dict[str, Any]:
    return {
        "notifyId": row.notifyId,
        "dedupKey": row.dedupKey,
        "channel": row.targetKind,
        "targetId": row.targetId,
        "title": row.title,
        "content": row.content,
        "scheduledAt": row.scheduledAt,
        "sentAt": row.sentAt,
        "stat": row.stat,
        "failReason": row.failReason,
    }


def _msgLogDict(row: MsgLog) -> dict[str, Any]:
    return {
        "msgId": row.msgId,
        "src": row.src,
        "externalId": row.externalId,
        "rawText": row.rawText,
        "intent": row.intent,
        "stat": row.stat,
        "createdAt": row.createdAt,
    }


def _actLogDict(row: ActLog) -> dict[str, Any]:
    return {
        "actId": row.actId,
        "src": row.src,
        "actor": row.actor,
        "actType": row.actType,
        "targetKind": row.targetKind,
        "targetId": row.targetId,
        "beforeData": row.beforeData,
        "afterData": row.afterData,
        "undoToken": row.undoToken,
        "createdAt": row.createdAt,
    }


def _recordAct(
    db: Session,
    *,
    src: str,
    actType: str,
    targetKind: str | None,
    targetId: str | None,
    beforeData: dict | None,
    afterData: dict | None,
    actor: str | None = None,
    undoToken: str | None = None,
) -> ActLog:
    row = ActLog(
        src=src,
        actor=actor,
        actType=actType,
        targetKind=targetKind,
        targetId=targetId,
        beforeData=beforeData,
        afterData=afterData,
        undoToken=undoToken,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def createLifeEvt(
    db: Session,
    *,
    title: str,
    dueAt: str | None,
    src: str,
    desc: str | None = None,
    prio: str = "mid",
) -> dict[str, Any]:
    evtId = newId()
    base = EvtBase(evtId=evtId, title=title, desc=desc, evtType="life", prio=prio, stat="todo")
    db.add(base)
    db.flush()
    life = LifeEvt(evtId=base.evtId, dueAt=dueAt)
    db.add(life)
    db.commit()
    db.refresh(base)
    db.refresh(life)
    result = _lifeDict(base, life)
    _recordAct(
        db,
        src=src,
        actType="create",
        targetKind="lifeEvt",
        targetId=base.evtId,
        beforeData=None,
        afterData=result,
        undoToken=secrets.token_urlsafe(16),
    )
    return result


def createDdlEvt(
    db: Session,
    *,
    title: str,
    ddlAt: str | None,
    hardDdl: bool = False,
    src: str,
    desc: str | None = None,
    prio: str = "mid",
) -> dict[str, Any]:
    evtId = newId()
    base = EvtBase(evtId=evtId, title=title, desc=desc, evtType="ddl", prio=prio, stat="todo")
    db.add(base)
    db.flush()
    ddl = DdlEvt(evtId=base.evtId, ddlAt=ddlAt, hardDdl=hardDdl)
    db.add(ddl)
    db.commit()
    db.refresh(base)
    db.refresh(ddl)
    result = _ddlDict(base, ddl)
    _recordAct(
        db,
        src=src,
        actType="create",
        targetKind="ddlEvt",
        targetId=base.evtId,
        beforeData=None,
        afterData=result,
        undoToken=secrets.token_urlsafe(16),
    )
    return result


def createCourseTpl(db: Session, **fields: Any) -> dict[str, Any]:
    tpl = CourseTpl(**fields)
    db.add(tpl)
    db.commit()
    db.refresh(tpl)
    result = _courseTplDict(tpl)
    _recordAct(
        db,
        src="api",
        actType="create",
        targetKind="courseTpl",
        targetId=tpl.tplId,
        beforeData=None,
        afterData=result,
        undoToken=secrets.token_urlsafe(16),
    )
    return result


def createCourseInst(
    db: Session,
    *,
    title: str,
    tplId: str,
    classDate: str | None,
    attendStat: str = "unknown",
    src: str = "api",
) -> dict[str, Any]:
    evtId = newId()
    base = EvtBase(evtId=evtId, title=title, evtType="course", stat="todo")
    db.add(base)
    db.flush()
    inst = CourseInst(evtId=base.evtId, tplId=tplId, classDate=classDate, attendStat=attendStat)
    db.add(inst)
    db.commit()
    db.refresh(base)
    db.refresh(inst)
    result = _courseInstDict(base, inst)
    _recordAct(
        db,
        src=src,
        actType="create",
        targetKind="courseInst",
        targetId=base.evtId,
        beforeData=None,
        afterData=result,
        undoToken=secrets.token_urlsafe(16),
    )
    return result


def createIdea(
    db: Session,
    *,
    content: str,
    srcType: str = "text",
    mediaPath: str | None = None,
) -> dict[str, Any]:
    idea = Idea(content=content, srcType=srcType, mediaPath=mediaPath)
    db.add(idea)
    db.commit()
    db.refresh(idea)
    result = _ideaDict(idea)
    _recordAct(
        db,
        src="api",
        actType="create",
        targetKind="idea",
        targetId=idea.ideaId,
        beforeData=None,
        afterData=result,
        undoToken=secrets.token_urlsafe(16),
    )
    return result


def ideaToLifeEvt(
    db: Session,
    *,
    ideaId: str,
    title: str,
    dueAt: str | None,
    src: str,
) -> dict[str, Any]:
    idea = db.get(Idea, ideaId)
    if idea is None:
        raise ValueError(f"idea not found: {ideaId}")
    event = createLifeEvt(db, title=title, dueAt=dueAt, src=src)
    idea.handled = True
    link = IdeaToEvt(ideaId=ideaId, evtId=event["evtId"])
    db.add(link)
    db.commit()
    return event


def listEvt(db: Session) -> list[dict[str, Any]]:
    rows = db.scalars(select(EvtBase).order_by(EvtBase.createdAt.asc())).all()
    results: list[dict[str, Any]] = []
    for base in rows:
        if base.evtType == "life":
            life = db.get(LifeEvt, base.evtId)
            if life:
                results.append(_lifeDict(base, life))
        elif base.evtType == "ddl":
            ddl = db.get(DdlEvt, base.evtId)
            if ddl:
                results.append(_ddlDict(base, ddl))
        elif base.evtType == "course":
            inst = db.get(CourseInst, base.evtId)
            if inst:
                results.append(_courseInstDict(base, inst))
    return results


def listLifeEvt(db: Session) -> list[dict[str, Any]]:
    return [item for item in listEvt(db) if item["evtType"] == "life"]


def listDdlEvt(db: Session) -> list[dict[str, Any]]:
    return [item for item in listEvt(db) if item["evtType"] == "ddl"]


def listCourseInst(db: Session) -> list[dict[str, Any]]:
    return [item for item in listEvt(db) if item["evtType"] == "course"]


def listCourseTpl(db: Session) -> list[dict[str, Any]]:
    rows = db.scalars(select(CourseTpl).order_by(CourseTpl.courseName.asc())).all()
    return [_courseTplDict(row) for row in rows]


def listIdeas(db: Session) -> list[dict[str, Any]]:
    rows = db.scalars(select(Idea).order_by(Idea.createdAt.asc())).all()
    return [_ideaDict(row) for row in rows]


def listDevState(db: Session) -> list[dict[str, Any]]:
    rows = db.scalars(select(DevState).order_by(DevState.seenAt.desc())).all()
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
        select(DevState)
        .where(DevState.devId == devId)
        .order_by(DevState.seenAt.desc())
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
    row = DevState(
        devId=devId,
        state=state,
        confidence=confidence,
        seenAt=seenAt or nowIso(),
        meta=meta,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _devStateDict(row)


def updateEvt(db: Session, evtId: str, **fields: Any) -> dict[str, Any]:
    base = db.get(EvtBase, evtId)
    if base is None:
        raise ValueError(f"evt not found: {evtId}")
    before = listEvt(db)
    before_item = next((item for item in before if item["evtId"] == evtId), None)
    for key in ("title", "desc", "prio", "stat"):
        if key in fields and fields[key] is not None:
            setattr(base, key, fields[key])
    base.updatedAt = nowIso()
    db.commit()
    db.refresh(base)
    after = next(item for item in listEvt(db) if item["evtId"] == evtId)
    _recordAct(
        db,
        src="api",
        actType="update",
        targetKind=base.evtType + "Evt",
        targetId=evtId,
        beforeData=before_item,
        afterData=after,
        undoToken=secrets.token_urlsafe(16),
    )
    return after


def cancelEvt(db: Session, evtId: str, *, src: str = "api") -> dict[str, Any]:
    base = db.get(EvtBase, evtId)
    if base is None:
        raise ValueError(f"evt not found: {evtId}")
    before = next(item for item in listEvt(db) if item["evtId"] == evtId)
    base.stat = "cancelled"
    base.updatedAt = nowIso()
    db.commit()
    db.refresh(base)
    after = next(item for item in listEvt(db) if item["evtId"] == evtId)
    _recordAct(
        db,
        src=src,
        actType="delete",
        targetKind=base.evtType + "Evt",
        targetId=evtId,
        beforeData=before,
        afterData=after,
        undoToken=secrets.token_urlsafe(16),
    )
    return after


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
    row = NotifyLog(
        dedupKey=dedupKey,
        targetKind=channel,
        targetId=targetId,
        title=title,
        content=content,
        scheduledAt=nowIso(),
        sentAt=nowIso(),
        stat=stat,
        failReason=failReason,
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
    row = MsgLog(
        src=src,
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
    return (
        db.scalars(
            select(MsgLog).where(MsgLog.src == src, MsgLog.externalId == externalId)
        ).first()
        is not None
    )


def undoByToken(db: Session, undoToken: str) -> dict[str, Any]:
    row = db.scalars(select(ActLog).where(ActLog.undoToken == undoToken)).first()
    if row is None:
        raise ValueError("undo token not found")
    if row.actType == "create" and row.targetId and row.afterData:
        base = db.get(EvtBase, row.targetId)
        if base is not None:
            base.stat = "cancelled"
            base.updatedAt = nowIso()
        elif row.targetKind == "idea":
            idea = db.get(Idea, row.targetId)
            if idea is not None:
                db.delete(idea)
        elif row.targetKind == "courseTpl":
            tpl = db.get(CourseTpl, row.targetId)
            if tpl is not None:
                db.delete(tpl)
        db.commit()
    _recordAct(
        db,
        src="api",
        actType="undo",
        targetKind=row.targetKind,
        targetId=row.targetId,
        beforeData=row.afterData,
        afterData=row.beforeData,
    )
    return {"ok": True, "stat": "done"}
