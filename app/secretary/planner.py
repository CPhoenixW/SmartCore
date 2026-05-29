from __future__ import annotations

from datetime import date, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.secretary.assignments import get_assignments_due_on
from app.secretary.life_events import get_life_events_for_date, get_unscheduled_life_events
from app.secretary.rules import DEFAULT_TZ, DayPlan, PlanItem, format_datetime
from app.secretary.timetable import get_course_instances_for_date


def build_day_plan(
    db: Session,
    target: date,
    *,
    tz: ZoneInfo = DEFAULT_TZ,
    semester_start: date | None = None,
    include_unscheduled: bool = False,
) -> DayPlan:
    plan = DayPlan(target_date=target)

    for course in get_course_instances_for_date(db, target, semester_start=semester_start):
        time_label = None
        if course.start_time and course.end_time:
            time_label = f"{course.start_time}-{course.end_time}"
        elif course.start_time:
            time_label = course.start_time
        plan.courses.append(
            PlanItem(
                kind="course",
                title=course.course_name,
                time_label=time_label,
                location=course.location,
                ref_id=course.session_id,
            )
        )

    for assignment in get_assignments_due_on(db, target, tz):
        plan.assignments.append(
            PlanItem(
                kind="assignment",
                title=assignment.title,
                time_label=format_datetime(assignment.due_at, tz),
                notes=assignment.notes,
                ref_id=assignment.id,
            )
        )

    for event in get_life_events_for_date(db, target, tz):
        plan.life_events.append(
            PlanItem(
                kind="life_event",
                title=event.title,
                time_label=format_datetime(event.scheduled_at, tz),
                notes=event.notes,
                ref_id=event.id,
            )
        )

    if include_unscheduled:
        for event in get_unscheduled_life_events(db):
            plan.unscheduled.append(
                PlanItem(
                    kind="life_event",
                    title=event.title,
                    notes=event.notes,
                    ref_id=event.id,
                )
            )

    return plan


def build_today_plan(
    db: Session,
    *,
    today: date | None = None,
    tz: ZoneInfo = DEFAULT_TZ,
    semester_start: date | None = None,
) -> DayPlan:
    target = today or date.today()
    return build_day_plan(
        db,
        target,
        tz=tz,
        semester_start=semester_start,
        include_unscheduled=True,
    )


def build_tomorrow_plan(
    db: Session,
    *,
    today: date | None = None,
    tz: ZoneInfo = DEFAULT_TZ,
    semester_start: date | None = None,
) -> DayPlan:
    base = today or date.today()
    return build_day_plan(
        db,
        base + timedelta(days=1),
        tz=tz,
        semester_start=semester_start,
        include_unscheduled=False,
    )
