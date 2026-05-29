from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session, joinedload

from app.db.models import CourseSession, WeekRule


@dataclass(frozen=True)
class CourseInstance:
    course_id: int
    course_name: str
    weekday: int
    start_time: str | None
    end_time: str | None
    location: str | None
    session_id: int


def _week_number(target: date, semester_start: date) -> int:
    delta_days = (target - semester_start).days
    return delta_days // 7 + 1


def session_applies_on_date(
    session: CourseSession,
    target: date,
    *,
    semester_start: date | None = None,
) -> bool:
    if target.isoweekday() != session.weekday:
        return False

    rule = session.week_rule or WeekRule.EVERY.value
    if rule == WeekRule.EVERY.value:
        return True

    if semester_start is None:
        semester_start = date(target.year, 9, 1)

    week_no = _week_number(target, semester_start)

    if rule == WeekRule.ODD.value:
        return week_no % 2 == 1
    if rule == WeekRule.EVEN.value:
        return week_no % 2 == 0
    if rule == WeekRule.RANGE.value and session.week_range:
        start_s, end_s = session.week_range.split("-", 1)
        start_w, end_w = int(start_s), int(end_s)
        return start_w <= week_no <= end_w
    return False


def resolve_location(session: CourseSession) -> str | None:
    if session.location_override:
        return session.location_override
    return session.course.default_location if session.course else None


def get_course_instances_for_date(
    db: Session,
    target: date,
    *,
    semester_start: date | None = None,
) -> list[CourseInstance]:
    sessions = db.query(CourseSession).options(joinedload(CourseSession.course)).all()
    instances: list[CourseInstance] = []
    for session in sessions:
        if not session_applies_on_date(session, target, semester_start=semester_start):
            continue
        instances.append(
            CourseInstance(
                course_id=session.course_id,
                course_name=session.course.name,
                weekday=session.weekday,
                start_time=session.start_time,
                end_time=session.end_time,
                location=resolve_location(session),
                session_id=session.id,
            )
        )
    instances.sort(key=lambda item: item.start_time or "99:99")
    return instances


def local_day_bounds(target: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    start = datetime.combine(target, time.min, tzinfo=tz)
    end = start + timedelta(days=1)
    return start, end
