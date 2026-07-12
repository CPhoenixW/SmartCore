from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import require_authenticated_user_id
from app.db.session import get_db
from app.new_core import crud
from app.new_core.ddl_service import create_ddl_event, replace_ddl_plans
from app.new_core.event_relations import (
    cancel_event,
    create_course_event,
    create_plan_event,
    ensure_all_relations,
    get_event,
    list_course_events,
    list_events,
    sync_course_plans,
    update_event,
)
from app.new_core.models import ActLog, DeviceStateLog, EvtBase, MsgLog, NotifyLog, nowIso
from app.new_core.preferences import get_user_preferences, update_user_preferences
from app.new_core.reminder_service import (
    create_reminder_event,
    get_reminder_event,
    list_reminder_events,
    update_reminder_event,
)

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
        "cannot be edited",
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
def get_user_me(userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db)) -> dict[str, Any]:
    user = crud.getCurrentUser(db, userId=userId)
    user.update(get_user_preferences(db, user_id=userId))
    db.commit()
    return ok(user)


@router.patch("/user/me")
def patch_user_me(
    body: UserPatchBody,
    userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        user_fields = body.model_dump(exclude={"reminderChannel"})
        user = crud.updateCurrentUser(db, userId=userId, **user_fields)
        preferences = update_user_preferences(
            db,
            reminder_channel=body.reminderChannel,
            user_id=userId,
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
    userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db),
) -> dict[str, Any]:
    include_templates = date is None if includeCourseTemplates is None else includeCourseTemplates
    try:
        rows = list_events(
            db,
            user_id=userId,
            date_value=date,
            evt_types=evtType,
            stats=stat,
            text=text,
            include_reminders=False,
            include_course_templates=include_templates,
        )
        if includeReminders and (not evtType or "remind" in evtType):
            rows.extend(
                list_reminder_events(
                    db,
                    user_id=userId,
                    date_value=date,
                    stats=stat,
                    text=text,
                )
            )
        return ok(rows)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.get("/evt/{evtId}")
def read_evt(
    evtId: str,
    userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        base = db.get(EvtBase, evtId)
        if base is None or base.userId != userId:
            raise ValueError(f"evt not found: {evtId}")
        return ok(get_reminder_event(db, evtId) if base.evtType == "remind" else get_event(db, evtId))
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.patch("/evt/{evtId}")
def patch_evt(
    evtId: str,
    body: dict[str, Any],
    userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        base = db.get(EvtBase, evtId)
        if base is None or base.userId != userId:
            raise ValueError(f"evt not found: {evtId}")
        if base.evtType == "remind":
            return ok(update_reminder_event(db, evtId, src="api", **body))
        plans = body.pop("plans", None)
        result = update_event(db, evtId, src="api", **body)
        if base.evtType == "ddl" and plans is not None:
            result = replace_ddl_plans(db, evtId, plans, src="api")
        return ok(result)
    except ValueError as exc:
        db.rollback()
        raise _http_error(exc) from exc


@router.delete("/evt/{evtId}")
def delete_evt(evtId: str, userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        base = db.get(EvtBase, evtId)
        if base is None or base.userId != userId:
            raise ValueError(f"evt not found: {evtId}")
        return ok(cancel_event(db, evtId, src="api"))
    except ValueError as exc:
        db.rollback()
        raise _http_error(exc) from exc


class PlanEvtBody(BaseModel):
    title: str
    stTime: str
    durationMin: int = Field(default=30, gt=0)
    desc: str | None = None
    prio: str = "mid"


@router.get("/planEvt")
def list_plan_evt(
    date: str | None = None,
    userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db),
) -> dict[str, Any]:
    return ok(
        list_events(
            db,
            user_id=userId,
            date_value=date,
            evt_types=["plan"],
            include_course_templates=False,
        )
    )


@router.post("/planEvt")
def create_plan_evt(body: PlanEvtBody, userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return ok(create_plan_event(db, **body.model_dump(), userId=userId, src="api"))
    except ValueError as exc:
        db.rollback()
        raise _http_error(exc) from exc


class RemindEvtBody(BaseModel):
    title: str
    triggerTime: str
    desc: str | None = None
    prio: str = "mid"


@router.get("/remindEvt")
def list_remind_evt(
    date: str | None = None,
    stat: list[str] | None = Query(default=None),
    text: str | None = None,
    userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db),
) -> dict[str, Any]:
    return ok(list_reminder_events(db, user_id=userId, date_value=date, stats=stat, text=text))


@router.post("/remindEvt")
def create_remind_evt(body: RemindEvtBody, userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return ok(create_reminder_event(db, **body.model_dump(), userId=userId, src="api"))
    except ValueError as exc:
        db.rollback()
        raise _http_error(exc) from exc


class DdlPlanBody(BaseModel):
    planEvtId: str | None = None
    planRole: Literal["one_day_before", "one_hour_before", "manual"] = "manual"
    stTime: str
    durationMin: int = Field(default=30, gt=0)
    title: str | None = None
    desc: str | None = None
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
def list_ddl_evt(userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(list_events(db, user_id=userId, evt_types=["ddl"], include_course_templates=False))


@router.post("/ddlEvt")
def create_ddl_evt(body: DdlEvtBody, userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        payload = body.model_dump()
        payload["plans"] = (
            [plan.model_dump(exclude_none=True) for plan in body.plans]
            if body.plans is not None
            else None
        )
        return ok(create_ddl_event(db, **payload, userId=userId, src="api"))
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
def list_course_evt(userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(list_course_events(db, user_id=userId))


@router.post("/courseEvt")
def create_course_evt(body: CourseEvtBody, userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return ok(create_course_event(db, **body.model_dump(), userId=userId, src="api"))
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
def list_idea(userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(crud.listIdeas(db, userId=userId))


@router.post("/idea")
def create_idea(body: IdeaBody, userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(
        crud.createIdea(
            db,
            content=body.content,
            srcType=body.srcType,
            mediaPath=body.mediaPath,
            userId=userId,
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
    query = select(DeviceStateLog)
    if devId:
        query = query.where(DeviceStateLog.deviceId == devId)
    rows = db.scalars(
        query.order_by(DeviceStateLog.seenAt.desc()).limit(limit)
    ).all()
    return ok([_row_dict(row) for row in rows])


@router.get("/log")
def list_logs(
    limit: int = Query(default=120, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return ok(
        {
            "act": _latest_rows(db, ActLog, ActLog.createdAt, limit=limit),
            "notify": _latest_rows(db, NotifyLog, NotifyLog.scheduledAt, limit=limit),
            "msg": _latest_rows(db, MsgLog, MsgLog.createdAt, limit=limit),
        }
    )


@router.get("/log/act")
def list_log_act(
    limit: int = Query(default=120, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return ok(_latest_rows(db, ActLog, ActLog.createdAt, limit=limit))


@router.get("/log/notify")
def list_log_notify(
    limit: int = Query(default=120, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return ok(_latest_rows(db, NotifyLog, NotifyLog.scheduledAt, limit=limit))


@router.get("/log/msg")
def list_log_msg(
    limit: int = Query(default=120, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return ok(_latest_rows(db, MsgLog, MsgLog.createdAt, limit=limit))


class ReminderActionBody(BaseModel):
    evtId: str
    action: str
    now: str | None = None


@router.post("/reminder/action")
def reminder_action(
    body: ReminderActionBody,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    from app.new_core.event_relations import apply_reminder_action

    try:
        return ok(
            apply_reminder_action(
                db,
                evt_id=body.evtId,
                action=body.action,
                now=body.now or nowIso(),
                src="screen",
            )
        )
    except ValueError as exc:
        db.rollback()
        raise _http_error(exc) from exc
