from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.security import require_authenticated_user_id
from app.db.session import get_db
from app.new_core.course_semester import (
    create_course_event,
    get_course_event,
    list_course_events,
    sync_course_plans,
    update_course_event,
)
from app.new_core.ddl_service import replace_ddl_plans, replace_ddl_reminders
from app.new_core.event_relations import (
    apply_reminder_action,
    cancel_event,
    get_event,
    list_events,
    update_event,
)
from app.new_core.event_search import filter_events_by_text
from app.new_core.models import EvtBase, RemindEvt, nowIso
from app.new_core.relation_maintenance import close_past_course_occurrences
from app.new_core.reminder_service import (
    get_reminder_event,
    list_reminder_events,
    update_reminder_event,
)

router = APIRouter(prefix="/api", tags=["event-view"])
_DEFAULT_TZ = ZoneInfo("Asia/Shanghai")


def _error(exc: ValueError) -> HTTPException:
    message = str(exc)
    status = 404 if "not found" in message else 400
    return HTTPException(status_code=status, detail=message)


def _parse_now(value: str | None) -> datetime:
    if not value:
        return datetime.now(_DEFAULT_TZ)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_DEFAULT_TZ)
    return parsed.astimezone(_DEFAULT_TZ)


@router.get("/evt")
def list_actionable_events(
    date: str | None = None,
    evtType: list[str] | None = Query(default=None),
    stat: list[str] | None = Query(default=None),
    text: str | None = None,
    includeReminders: bool = False,
    includeCourseTemplates: bool = False,
    userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        non_reminder_types = [item for item in (evtType or []) if item != "remind"]
        rows = []
        if not evtType or non_reminder_types:
            rows = list_events(
                db,
                user_id=userId,
                date_value=date,
                evt_types=non_reminder_types or None,
                stats=stat,
                text=None,
                include_reminders=False,
                include_course_templates=includeCourseTemplates,
            )
        if includeReminders and (not evtType or "remind" in evtType):
            rows.extend(
                list_reminder_events(
                    db,
                    user_id=userId,
                    date_value=date,
                    stats=stat,
                    text=None,
                )
            )
        return {"ok": True, "data": filter_events_by_text(rows, text)}
    except ValueError as exc:
        raise _error(exc) from exc


@router.get("/evt/{evtId}")
def read_actionable_event(
    evtId: str,
    userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        base = db.get(EvtBase, evtId)
        if base is None or base.userId != userId:
            raise ValueError(f"evt not found: {evtId}")
        if base.evtType == "course":
            data = get_course_event(db, evtId)
        elif base.evtType == "remind":
            data = get_reminder_event(db, evtId)
        else:
            data = get_event(db, evtId)
        return {"ok": True, "data": data}
    except ValueError as exc:
        raise _error(exc) from exc


@router.patch("/evt/{evtId}")
def update_actionable_event(
    evtId: str,
    body: dict[str, Any],
    userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        base = db.get(EvtBase, evtId)
        if base is None or base.userId != userId:
            raise ValueError(f"evt not found: {evtId}")
        plans = body.pop("plans", None)
        ddl_reminders = body.pop("ddlReminders", None)
        if base.evtType == "course":
            result = update_course_event(db, evtId, src="api", **body)
        elif base.evtType == "remind":
            result = update_reminder_event(db, evtId, src="api", **body)
        else:
            result = update_event(db, evtId, src="api", **body)
            if base.evtType == "ddl" and plans is not None:
                result = replace_ddl_plans(db, evtId, plans, src="api")
            if base.evtType == "ddl" and ddl_reminders is not None:
                result = replace_ddl_reminders(db, evtId, ddl_reminders, src="api")
        close_past_course_occurrences(db)
        return {"ok": True, "data": result}
    except ValueError as exc:
        db.rollback()
        raise _error(exc) from exc


@router.delete("/evt/{evtId}")
def cancel_actionable_event(evtId: str, userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        base = db.get(EvtBase, evtId)
        if base is None or base.userId != userId:
            raise ValueError(f"evt not found: {evtId}")
        if base.evtType == "remind":
            return {"ok": True, "data": update_reminder_event(db, evtId, src="api", stat="cancelled")}
        return {"ok": True, "data": cancel_event(db, evtId, src="api")}
    except ValueError as exc:
        db.rollback()
        raise _error(exc) from exc


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
        remind = db.get(RemindEvt, body.evtId)
        if remind is not None and remind.planEvtId is None:
            if body.action == "done":
                return {"ok": True, "data": update_reminder_event(db, body.evtId, src="screen", stat="done")}
            if body.action == "snooze10":
                trigger = _parse_now(body.now) + timedelta(minutes=10)
                return {
                    "ok": True,
                    "data": update_reminder_event(
                        db,
                        body.evtId,
                        src="screen",
                        triggerTime=trigger.isoformat(),
                        stat="todo",
                    ),
                }
            raise ValueError(f"unknown reminder action: {body.action}")
        return {
            "ok": True,
            "data": apply_reminder_action(
                db,
                evt_id=body.evtId,
                action=body.action,
                now=body.now or nowIso(),
                src="screen",
            ),
        }
    except ValueError as exc:
        db.rollback()
        raise _error(exc) from exc


class CourseWriteBody(BaseModel):
    title: str | None = None
    courseName: str
    teacher: str | None = None
    location: str | None = None
    stTime: str
    endTime: str
    semesterStart: str | None = None
    stDate: str | None = None
    endDate: str | None = None
    weekDay: int | str
    startWeek: int = Field(default=1, ge=1)
    endWeek: int = Field(default=16, ge=1)
    weekMode: Literal["all", "odd", "even"] = "all"
    desc: str | None = None
    prio: str = "mid"


@router.get("/courseEvt")
def list_relation_courses(
    text: str | None = None,
    userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db),
) -> dict[str, Any]:
    rows = list_course_events(db, user_id=userId)
    return {"ok": True, "data": filter_events_by_text(rows, text)}


@router.post("/courseEvt")
def create_relation_course(
    body: CourseWriteBody,
    userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        result = create_course_event(db, **body.model_dump(exclude_none=True), userId=userId, src="api")
        close_past_course_occurrences(db)
        return {"ok": True, "data": result}
    except ValueError as exc:
        db.rollback()
        raise _error(exc) from exc


@router.post("/courseEvt/{evtId}/sync")
def resync_relation_course(evtId: str, userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        base = db.get(EvtBase, evtId)
        if base is None or base.userId != userId:
            raise ValueError(f"evt not found: {evtId}")
        plans = sync_course_plans(db, evtId)
        db.commit()
        close_past_course_occurrences(db)
        return {
            "ok": True,
            "data": {
                "course": get_course_event(db, evtId),
                "plans": plans,
            },
        }
    except ValueError as exc:
        db.rollback()
        raise _error(exc) from exc
