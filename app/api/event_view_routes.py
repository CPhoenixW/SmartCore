from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.new_core.event_relations import list_events

router = APIRouter(prefix="/api", tags=["event-view"])


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
        raise HTTPException(status_code=400, detail=str(exc)) from exc
