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


def _http_error(exc: ValueError) -> HTTPException:
    msg = str(exc)
    if "required" in msg or "disabled" in msg:
        return HTTPException(status_code=400, detail=msg)
    return HTTPException(status_code=404, detail=msg)


@router.get("/evt")
def list_evt(db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(crud.listEvt(db))


@router.patch("/evt/{evtId}")
def patch_evt(evtId: str, body: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return ok(crud.updateEvt(db, evtId, **body))
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.delete("/evt/{evtId}")
def delete_evt(evtId: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return ok(crud.cancelEvt(db, evtId))
    except ValueError as exc:
        raise _http_error(exc) from exc


class PlanEvtBody(BaseModel):
    title: str
    stTime: str
    durationMin: int = 30
    desc: str | None = None
    prio: str = "mid"


@router.get("/planEvt")
def list_plan_evt(db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(crud.listPlanEvt(db))


@router.post("/planEvt")
def create_plan_evt(body: PlanEvtBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(crud.createPlanEvt(db, **body.model_dump(), src="api"))


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
    return ok(crud.createLifeEvt(db, title=body.title, dueAt=body.dueAt, src="api", desc=body.desc, prio=body.prio))


class DdlEvtBody(BaseModel):
    title: str
    endTime: str | None = None
    ddlAt: str | None = None
    hardDdl: bool = False
    desc: str | None = None
    prio: str = "high"


@router.get("/ddlEvt")
def list_ddl_evt(db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(crud.listDdlEvt(db))


@router.post("/ddlEvt")
def create_ddl_evt(body: DdlEvtBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return ok(crud.createDdlEvt(db, **body.model_dump(), src="api"))
    except ValueError as exc:
        raise _http_error(exc) from exc


class CourseEvtBody(BaseModel):
    title: str | None = None
    courseName: str
    teacher: str | None = None
    location: str | None = None
    room: str | None = None
    stTime: str | None = None
    startTime: str | None = None
    endTime: str
    stDate: str
    endDate: str
    weekDay: int | None = None
    weekday: int | None = None
    startWeek: int | None = None
    endWeek: int | None = None
    weekMode: str = "all"
    desc: str | None = None
    prio: str = "mid"


@router.get("/courseEvt")
def list_course_evt(db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(crud.listCourseEvt(db))


@router.post("/courseEvt")
def create_course_evt(body: CourseEvtBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return ok(crud.createCourseEvt(db, **body.model_dump(), src="api"))
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.get("/courseTpl")
def list_course_tpl(db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(crud.listCourseTpl(db))


@router.post("/courseTpl")
def create_course_tpl(body: CourseEvtBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return ok(crud.createCourseEvt(db, **body.model_dump(), src="api"))
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.patch("/courseTpl/{tplId}")
def patch_course_tpl(tplId: str, body: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return ok(crud.updateEvt(db, tplId, **body))
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.delete("/courseTpl/{tplId}")
def delete_course_tpl(tplId: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return ok(crud.cancelEvt(db, tplId))
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.get("/courseInst")
def list_course_inst(db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(crud.listCourseInst(db))


class IdeaBody(BaseModel):
    content: str
    srcType: str = "text"
    mediaPath: str | None = None


class IdeaPatchBody(BaseModel):
    content: str | None = None
    handled: bool | None = None


@router.get("/idea")
def list_idea(db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(crud.listIdeas(db))


@router.post("/idea")
def create_idea(body: IdeaBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(crud.createIdea(db, content=body.content, srcType=body.srcType, mediaPath=body.mediaPath))


@router.patch("/idea/{ideaId}")
def patch_idea(ideaId: str, body: IdeaPatchBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        from app.new_core.models import Idea

        row = db.get(Idea, ideaId)
        if row is None:
            raise ValueError(f"idea not found: {ideaId}")
        if body.content is not None:
            row.content = body.content
        if body.handled is not None:
            row.handled = body.handled
        row_dict = crud._ideaDict(row)  # noqa: SLF001
        crud._recordAct(db, userId=row.userId, src="api", action="update", targetKind="idea", targetId=ideaId)  # noqa: SLF001
        db.commit()
        return ok(row_dict)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.delete("/idea/{ideaId}")
def delete_idea(ideaId: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        from app.new_core.models import Idea

        row = db.get(Idea, ideaId)
        if row is None:
            raise ValueError(f"idea not found: {ideaId}")
        data = crud._ideaDict(row)  # noqa: SLF001
        crud._recordAct(db, userId=row.userId, src="api", action="delete", targetKind="idea", targetId=ideaId)  # noqa: SLF001
        db.delete(row)
        db.commit()
        return ok(data)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.post("/idea/{ideaId}/toEvt")
def idea_to_evt(ideaId: str) -> dict[str, Any]:
    raise HTTPException(status_code=410, detail="idea no longer converts to event")


@router.get("/devState")
def list_dev_state(db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(crud.listDevState(db))


@router.get("/log/act")
def list_log_act(db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(crud.listActLog(db))


@router.get("/log/notify")
def list_log_notify(db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(crud.listNotifyLog(db))


@router.get("/log/msg")
def list_log_msg(db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(crud.listMsgLog(db))


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
        raise _http_error(exc) from exc


class ReminderActionBody(BaseModel):
    evtId: str
    action: str
    now: str | None = None


@router.post("/reminder/action")
def reminder_action(body: ReminderActionBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return ok(crud.applyReminderAction(db, evtId=body.evtId, action=body.action, now=body.now or nowIso(), src="screen"))
    except ValueError as exc:
        raise _http_error(exc) from exc


class LlmParseBody(BaseModel):
    text: str
    scene: str = "create_event"


@router.post("/llm/parse")
def llm_parse_placeholder(body: LlmParseBody) -> dict[str, Any]:
    return ok({"status": "placeholder", "scene": body.scene, "text": body.text, "parsed": None})
