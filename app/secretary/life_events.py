from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.db.models import LifeEvent, LifeEventStatus
from app.secretary.timetable import local_day_bounds


def get_life_events_for_date(db: Session, target: date, tz: ZoneInfo) -> list[LifeEvent]:
    start, end = local_day_bounds(target, tz)
    return (
        db.query(LifeEvent)
        .filter(
            LifeEvent.status != LifeEventStatus.DONE.value,
            LifeEvent.status != LifeEventStatus.CANCELLED.value,
            LifeEvent.scheduled_at.isnot(None),
            LifeEvent.scheduled_at >= start,
            LifeEvent.scheduled_at < end,
        )
        .order_by(LifeEvent.scheduled_at.asc())
        .all()
    )


def get_unscheduled_life_events(db: Session) -> list[LifeEvent]:
    return (
        db.query(LifeEvent)
        .filter(
            LifeEvent.status != LifeEventStatus.DONE.value,
            LifeEvent.status != LifeEventStatus.CANCELLED.value,
            LifeEvent.scheduled_at.is_(None),
        )
        .order_by(LifeEvent.created_at.asc())
        .all()
    )
