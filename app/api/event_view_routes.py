from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.new_core.event_relations import (
    cancel_event,
    create_course_event,
    get_event,
    list_events,
    update_event,
)
from app.new_core.relation_maintenance import close_past_course_occurrences

router = APIRouter(prefix="/api", tags=["event-view"])


def _error(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/evt")
def list_actionable_events(
    date: str | None = None,
    evtType: list[str] | None = Query(default=None),
    stat: list[str] | None = Query(default=None),
    text: str | None = None,
    includeReminders: bool = False,
    includeCourseTemplates: bool = False,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        rows = list_events(
            db,
            date_value=date,
            evt_types=evtType,
            stats=stat,
            text=text,
            include_reminders=includeReminders,
            include_course_templates=includeCourseTemplates,
        )
        return {"ok": True, "data": rows}
    except ValueError as exc:
        raise _error(exc) from exc


@router.patch("/evt/{evtId}")
def update_actionable_event(
    evtId: str,
    body: dict[str, Any],
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        result = update_event(db, evtId, src="api", **body)
        close_past_course_occurrences(db)
        return {"ok": True, "data": get_event(db, result["evtId"])}
    except ValueError as exc:
        db.rollback()
        raise _error(exc) from exc


@router.delete("/evt/{evtId}")
def cancel_actionable_event(evtId: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return {"ok": True, "data": cancel_event(db, evtId, src="api")}
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
    stDate: str
    endDate: str
    weekDay: int | str
    startWeek: int | None = None
    endWeek: int | None = None
    weekMode: Literal["all", "odd", "even"] = "all"
    desc: str | None = None
    prio: str = "mid"


@router.post("/courseEvt")
def create_relation_course(
    body: CourseWriteBody,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        result = create_course_event(db, **body.model_dump(), src="api")
        close_past_course_occurrences(db)
        return {"ok": True, "data": get_event(db, result["evtId"])}
    except ValueError as exc:
        db.rollback()
        raise _error(exc) from exc
