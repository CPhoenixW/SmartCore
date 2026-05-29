from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.db.models import Assignment, AssignmentStatus
from app.secretary.timetable import local_day_bounds


def get_assignments_due_on(db: Session, target: date, tz: ZoneInfo) -> list[Assignment]:
    start, end = local_day_bounds(target, tz)
    end = end - timedelta(microseconds=1)
    return (
        db.query(Assignment)
        .filter(
            Assignment.due_at.isnot(None),
            Assignment.due_at >= start,
            Assignment.due_at <= end,
            Assignment.status != AssignmentStatus.DONE.value,
            Assignment.status != AssignmentStatus.CANCELLED.value,
        )
        .order_by(Assignment.due_at.asc())
        .all()
    )


def get_open_assignments(db: Session) -> list[Assignment]:
    return (
        db.query(Assignment)
        .filter(
            Assignment.status != AssignmentStatus.DONE.value,
            Assignment.status != AssignmentStatus.CANCELLED.value,
        )
        .order_by(Assignment.due_at.asc().nullslast())
        .all()
    )
