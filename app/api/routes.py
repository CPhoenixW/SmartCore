from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.new_core import crud
from app.new_core.models import nowIso

router = APIRouter(prefix="/api", tags=["api"])


def ok(data: Any) -> dict[str, Any]:
    return {"ok": True, "data": data}


@router.get("/evt")
def list_evt(db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(crud.listEvt(db))


@router.patch("/evt/{evtId}")
def patch_evt(evtId: str, body: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return ok(crud.updateEvt(db, evtId, **body))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/evt/{evtId}")
def delete_evt(evtId: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return ok(crud.cancelEvt(db, evtId))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


class LifeEvtBody(BaseModel):
    title: str
    dueAt: str | None = None
    desc: str | None = None
    prio: str = "mid"


@router.get("/lifeEvt")
def list_life_evt(db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(crud.listLifeEvt(db))


@router.post("/lifeEvt")
def create_life_evt(body: LifeEvtBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(
        crud.createLifeEvt(
            db,
            title=body.title,
            dueAt=body.dueAt,
            src="api",
            desc=body.desc,
            prio=body.prio,
        )
    )


class DdlEvtBody(BaseModel):
    title: str
    ddlAt: str | None = None
    hardDdl: bool = False
    desc: str | None = None
    prio: str = "mid"


@router.get("/ddlEvt")
def list_ddl_evt(db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(crud.listDdlEvt(db))


@router.post("/ddlEvt")
def create_ddl_evt(body: DdlEvtBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(
        crud.createDdlEvt(
            db,
            title=body.title,
            ddlAt=body.ddlAt,
            hardDdl=body.hardDdl,
            src="api",
            desc=body.desc,
            prio=body.prio,
        )
    )


class CourseTplBody(BaseModel):
    courseName: str
    teacher: str | None = None
    room: str | None = None
    weekday: int
    startTime: str | None = None
    endTime: str | None = None
    startWeek: int | None = None
    endWeek: int | None = None
    weekMode: str = "all"
    semester: str | None = None


@router.get("/courseTpl")
def list_course_tpl(db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(crud.listCourseTpl(db))


@router.post("/courseTpl")
def create_course_tpl(body: CourseTplBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(crud.createCourseTpl(db, **body.model_dump()))


class CourseInstBody(BaseModel):
    title: str
    tplId: str
    classDate: str | None = None
    attendStat: str = "unknown"


@router.get("/courseInst")
def list_course_inst(db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(crud.listCourseInst(db))


@router.post("/courseInst")
def create_course_inst(body: CourseInstBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(
        crud.createCourseInst(
            db,
            title=body.title,
            tplId=body.tplId,
            classDate=body.classDate,
            attendStat=body.attendStat,
        )
    )


class IdeaBody(BaseModel):
    content: str
    srcType: str = "text"
    mediaPath: str | None = None


@router.get("/idea")
def list_idea(db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(crud.listIdeas(db))


@router.post("/idea")
def create_idea(body: IdeaBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(
        crud.createIdea(
            db,
            content=body.content,
            srcType=body.srcType,
            mediaPath=body.mediaPath,
        )
    )


class IdeaToEvtBody(BaseModel):
    title: str
    dueAt: str | None = None


@router.post("/idea/{ideaId}/toEvt")
def idea_to_evt(ideaId: str, body: IdeaToEvtBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return ok(
            crud.ideaToLifeEvt(
                db,
                ideaId=ideaId,
                title=body.title,
                dueAt=body.dueAt,
                src="api",
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/devState")
def list_dev_state(db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(crud.listDevState(db))


@router.get("/notifyLog")
def list_notify_log(db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(crud.listNotifyLog(db))


@router.get("/msgLog")
def list_msg_log(db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(crud.listMsgLog(db))


@router.get("/actLog")
def list_act_log(db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(crud.listActLog(db))


@router.post("/undo/{undoToken}")
def undo_action(undoToken: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return crud.undoByToken(db, undoToken)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


class ReminderActionBody(BaseModel):
    evtId: str
    action: str
    now: str | None = None


@router.post("/reminder/action")
def reminder_action(body: ReminderActionBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return ok(
            crud.applyReminderAction(
                db,
                evtId=body.evtId,
                action=body.action,
                now=body.now or nowIso(),
                src="screen",
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
