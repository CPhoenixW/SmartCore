from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.new_core import crud
from app.new_core.custom_reminders import (
    list_extra_reminder_specs,
    replace_extra_reminders,
    sync_extra_reminders,
)
from app.new_core.ddl_service import create_ddl_event
from app.new_core.event_relations import (
    cancel_event,
    create_course_event,
    create_plan_event,
    ensure_all_relations,
    get_event,
    list_course_events,
    list_events,
    list_reminder_events,
    sync_course_plans,
    update_event,
)
from app.new_core.models import ActLog, DeviceStateLog, EvtBase, MsgLog, NotifyLog, nowIso
from app.new_core.preferences import get_user_preferences, update_user_preferences

router = APIRouter(prefix="/api", tags=["api"])


def ok(data: Any) -> dict[str, Any]:
    return {"ok": True, "data": data}


def _http_error(exc: ValueError) -> HTTPException:
    msg = str(exc)
    bad_request_terms = (
        "required",
        "disabled",
        "must be",
        "unsupported",
        "duplicate",
        "invalid",
        "earlier",
        "later",
        "managed automatically",
    )
    if any(term in msg for term in bad_request_terms):
        return HTTPException(status_code=400, detail=msg)
    return HTTPException(status_code=404, detail=msg)


def _row_dict(row: Any) -> dict[str, Any]:
    return {
        column.name: getattr(row, column.name)
        for column in row.__table__.columns
    }


def _latest_rows(
    db: Session,
    model: Any,
    order_field: Any,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(model).order_by(order_field.desc()).limit(limit)
    ).all()
    return [_row_dict(row) for row in rows]


class UserPatchBody(BaseModel):
    displayName: str | None = None
    language: str | None = None
    avatarUrl: str | None = None
    reminderChannel: Literal["screen", "feishu"] | None = None


@router.get("/user/me")
def get_user_me(db: Session = Depends(get_db)) -> dict[str, Any]:
    user = crud.getCurrentUser(db)
    user.update(get_user_preferences(db))
    db.commit()
    return ok(user)


@router.patch("/user/me")
def patch_user_me(
    body: UserPatchBody,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        user_fields = body.model_dump(exclude={"reminderChannel"})
        user = crud.updateCurrentUser(db, **user_fields)
        preferences = update_user_preferences(
            db,
            reminder_channel=body.reminderChannel,
        )
        user.update(preferences)
        return ok(user)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.get("/evt")
def list_evt(
    date: str | None = None,
    evtType: list[str] | None = Query(default=None),
    stat: list[str] | None = Query(default=None),
    text: str | None = None,
    includeReminders: bool = False,
    includeCourseTemplates: bool | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    include_templates = date is None if includeCourseTemplates is None else includeCourseTemplates
    try:
        return ok(
            list_events(
                db,
                date_value=date,
                evt_types=evtType,
                stats=stat,
                text=text,
                include_reminders=includeReminders,
                include_course_templates=include_templates,
            )
        )
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.get("/evt/{evtId}")
def read_evt(
    evtId: str,
    includeReminders: bool = False,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return ok(get_event(db, evtId, include_reminders=includeReminders))
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.patch("/evt/{evtId}")
def patch_evt(
    evtId: str,
    body: dict[str, Any],
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        base = db.get(EvtBase, evtId)
        extra_reminders = body.pop("extraReminders", None)
        result = update_event(db, evtId, src="api", **body)
        if base is not None and base.evtType == "plan":
            if extra_reminders is None:
                sync_extra_reminders(db, evtId)
            else:
                replace_extra_reminders(db, evtId, extra_reminders)
            result = get_event(db, evtId)
        return ok(result)
    except ValueError as exc:
        db.rollback()
        raise _http_error(exc) from exc


@router.delete("/evt/{evtId}")
def delete_evt(evtId: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return ok(cancel_event(db, evtId, src="api"))
    except ValueError as exc:
        db.rollback()
        raise _http_error(exc) from exc


class ReminderSpecBody(BaseModel):
    anchor: Literal["start", "end"] = "start"
    offsetMin: int = Field(default=10, ge=0, le=7 * 24 * 60)


class PlanEvtBody(BaseModel):
    title: str
    stTime: str
    durationMin: int = Field(default=30, gt=0)
    desc: str | None = None
    prio: str = "mid"
    extraReminders: list[ReminderSpecBody] = Field(default_factory=list)


@router.get("/planEvt")
def list_plan_evt(
    date: str | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return ok(
        list_events(
            db,
            date_value=date,
            evt_types=["plan"],
            include_course_templates=False,
        )
    )


@router.post("/planEvt")
def create_plan_evt(body: PlanEvtBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        payload = body.model_dump(exclude={"extraReminders"})
        result = create_plan_event(db, **payload, src="api", commit=False)
        replace_extra_reminders(
            db,
            result["evtId"],
            [item.model_dump() for item in body.extraReminders],
            commit=False,
        )
        db.commit()
        return ok(get_event(db, result["evtId"]))
    except ValueError as exc:
        db.rollback()
        raise _http_error(exc) from exc


class ReminderWriteBody(BaseModel):
    planEvtId: str
    anchor: Literal["start", "end"] = "start"
    offsetMin: int = Field(default=10, ge=0, le=7 * 24 * 60)


@router.post("/remindEvt")
def create_remind_evt(
    body: ReminderWriteBody,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        specs = list_extra_reminder_specs(db, body.planEvtId)
        specs.append({"anchor": body.anchor, "offsetMin": body.offsetMin})
        replace_extra_reminders(db, body.planEvtId, specs)
        return ok(get_event(db, body.planEvtId))
    except ValueError as exc:
        db.rollback()
        raise _http_error(exc) from exc


@router.put("/planEvt/{evtId}/reminders")
def replace_plan_reminders(
    evtId: str,
    body: list[ReminderSpecBody],
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        replace_extra_reminders(
            db,
            evtId,
            [item.model_dump() for item in body],
        )
        return ok(get_event(db, evtId))
    except ValueError as exc:
        db.rollback()
        raise _http_error(exc) from exc


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
    return ok(list_events(db, evt_types=["ddl"], include_course_templates=False))


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
        db.rollback()
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
    weekDay: int | str
    startWeek: int | None = None
    endWeek: int | None = None
    weekMode: Literal["all", "odd", "even"] = "all"
    desc: str | None = None
    prio: str = "mid"


@router.get("/courseEvt")
def list_course_evt(db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(list_course_events(db))


@router.post("/courseEvt")
def create_course_evt(body: CourseEvtBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return ok(create_course_event(db, **body.model_dump(), src="api"))
    except ValueError as exc:
        db.rollback()
        raise _http_error(exc) from exc


@router.post("/courseEvt/{evtId}/sync")
def sync_course_occurrences(evtId: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        plans = sync_course_plans(db, evtId)
        db.commit()
        return ok({"course": get_event(db, evtId), "plans": plans})
    except ValueError as exc:
        db.rollback()
        raise _http_error(exc) from exc


@router.get("/remindEvt")
def list_remind_evt(
    planEvtId: str | None = None,
    stat: str | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    rows = list_reminder_events(db)
    if planEvtId:
        rows = [row for row in rows if row.get("planEvtId") == planEvtId]
    if stat:
        rows = [row for row in rows if row.get("stat") == stat]
    return ok(rows)


@router.post("/evt/relations/sync")
def sync_all_event_relations(db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return ok(ensure_all_relations(db))
    except ValueError as exc:
        db.rollback()
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
    limit: int = Query(default=240, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    query = select(DeviceStateLog).order_by(DeviceStateLog.seenAt.desc()).limit(limit)
    if devId:
        query = query.where(DeviceStateLog.deviceId == devId)
    rows = db.scalars(query).all()
    return ok([_row_dict(row) for row in rows])


@router.get("/actLog")
def list_act_log(
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return ok(_latest_rows(db, ActLog, ActLog.createdAt, limit=limit))


@router.get("/notifyLog")
def list_notify_log(
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return ok(_latest_rows(db, NotifyLog, NotifyLog.createdAt, limit=limit))


@router.get("/msgLog")
def list_msg_log(
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return ok(_latest_rows(db, MsgLog, MsgLog.createdAt, limit=limit))


@router.get("/log")
def list_all_logs(
    limit: int = Query(default=120, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return ok(
        {
            "act": _latest_rows(db, ActLog, ActLog.createdAt, limit=limit),
            "notify": _latest_rows(db, NotifyLog, NotifyLog.createdAt, limit=limit),
            "msg": _latest_rows(db, MsgLog, MsgLog.createdAt, limit=limit),
        }
    )


@router.get("/time")
def get_time() -> dict[str, Any]:
    return ok({"now": nowIso(), "timezone": "Asia/Shanghai"})
