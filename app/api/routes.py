from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.new_core import crud
from app.new_core.ddl_service import create_ddl_event
from app.new_core.models import nowIso

router = APIRouter(prefix="/api", tags=["api"])


def ok(data: Any) -> dict[str, Any]:
    return {"ok": True, "data": data}


def _http_error(exc: ValueError) -> HTTPException:
    msg = str(exc)
    bad_request_terms = ("required", "disabled", "must be", "unsupported", "duplicate")
    if any(term in msg for term in bad_request_terms):
        return HTTPException(status_code=400, detail=msg)
    return HTTPException(status_code=404, detail=msg)


class UserPatchBody(BaseModel):
    displayName: str | None = None
    language: str | None = None
    avatarUrl: str | None = None


@router.get("/user/me")
def get_user_me(db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(crud.getCurrentUser(db))


@router.patch("/user/me")
def patch_user_me(body: UserPatchBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return ok(crud.updateCurrentUser(db, **body.model_dump()))
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.get("/evt")
def list_evt(db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(crud.listEvt(db))


@router.patch("/evt/{evtId}")
def patch_evt(
    evtId: str,
    body: dict[str, Any],
    db: Session = Depends(get_db),
) -> dict[str, Any]:
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


class DdlPlanBody(BaseModel):
    planRole: Literal["one_day_before", "one_hour_before", "manual"]
    stTime: str
    durationMin: int = Field(default=30, gt=0)
    title: str | None = None
    enabled: bool = True
    sortOrder: int | None = None


class DdlEvtBody(BaseModel):
    title: str
    endTime: str
    hardDdl: bool = False
    desc: str | None = None
    prio: str = "high"
    plans: list[DdlPlanBody] | None = None


@router.get("/ddlEvt")
def list_ddl_evt(db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(crud.listDdlEvt(db))


@router.post("/ddlEvt")
def create_ddl_evt(body: DdlEvtBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        payload = body.model_dump()
        payload["plans"] = (
            [plan.model_dump(exclude_none=True) for plan in body.plans]
            if body.plans is not None
            else None
        )
        return ok(create_ddl_event(db, **payload, src="api"))
    except ValueError as exc:
        raise _http_error(exc) from exc


class CourseEvtBody(BaseModel):
    title: str | None = None
    courseName: str
    teacher: str | None = None
    location: str | None = None
    stTime: str
    endTime: str
    stDate: str
    endDate: str
    weekDay: int
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
    return ok(
        crud.createIdea(
            db,
            content=body.content,
            srcType=body.srcType,
            mediaPath=body.mediaPath,
        )
    )


@router.patch("/idea/{ideaId}")
def patch_idea(
    ideaId: str,
    body: IdeaPatchBody,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return ok(
            crud.updateIdea(
                db,
                ideaId,
                content=body.content,
                handled=body.handled,
            )
        )
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.delete("/idea/{ideaId}")
def delete_idea(ideaId: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return ok(crud.deleteIdea(db, ideaId))
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.get("/devState")
def list_dev_state(
    devId: str | None = None,
    limit: int = Query(default=240, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    rows = crud.listDevState(db)
    if devId:
        rows = [row for row in rows if row.get("deviceId") == devId]
    return ok(rows[:limit])


@router.get("/log/act")
def list_log_act(db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(crud.listActLog(db))


@router.get("/log/notify")
def list_log_notify(db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(crud.listNotifyLog(db))


@router.get("/log/msg")
def list_log_msg(db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(crud.listMsgLog(db))


class ReminderActionBody(BaseModel):
    evtId: str
    action: str
    now: str | None = None


@router.post("/reminder/action")
def reminder_action(
    body: ReminderActionBody,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
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
        raise _http_error(exc) from exc
