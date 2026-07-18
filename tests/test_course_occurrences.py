from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.session import Base
from app.new_core.event_relations import (
    create_course_event,
    expand_course_dates,
    list_events,
    update_course_event,
)
from app.new_core.models import CoursePlan, RemindEvt


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return Session(engine)


def test_weekday_names_expand_to_matching_dates() -> None:
    dates = expand_course_dates(
        st_date="2026-09-01",
        end_date="2026-09-30",
        week_day="星期二",
        week_mode="all",
    )
    assert [value.isoformat() for value in dates] == [
        "2026-09-01",
        "2026-09-08",
        "2026-09-15",
        "2026-09-22",
        "2026-09-29",
    ]


def test_course_creates_one_plan_per_class_and_two_reminders_per_plan() -> None:
    db = _session()
    try:
        course = create_course_event(
            db,
            courseName="Robotics",
            teacher="Teacher Wang",
            location="A101",
            stTime="08:00",
            endTime="09:40",
            stDate="2026-09-01",
            endDate="2026-09-15",
            weekDay="星期二",
        )

        assert course["weekDay"] == 2
        assert course["occurrenceCount"] == 3
        assert [plan["occurrenceDate"] for plan in course["plans"]] == [
            "2026-09-01",
            "2026-09-08",
            "2026-09-15",
        ]
        assert all(plan["durationMin"] == 100 for plan in course["plans"])
        assert all(len(plan["reminders"]) == 2 for plan in course["plans"])
        assert db.scalar(select(CoursePlan).where(CoursePlan.courseEvtId == course["evtId"])) is not None
        assert len(db.scalars(select(RemindEvt)).all()) == 6
    finally:
        db.close()


def test_updating_course_regenerates_occurrences_without_duplicates() -> None:
    db = _session()
    try:
        course = create_course_event(
            db,
            courseName="Math",
            stTime="10:00",
            endTime="11:30",
            stDate="2026-09-01",
            endDate="2026-09-30",
            weekDay=2,
        )
        updated = update_course_event(
            db,
            course["evtId"],
            weekDay=4,
            stTime="14:00",
            endTime="15:30",
        )

        assert updated["weekDay"] == 4
        assert [plan["occurrenceDate"] for plan in updated["plans"]] == [
            "2026-09-03",
            "2026-09-10",
            "2026-09-17",
            "2026-09-24",
        ]
        assert len({plan["evtId"] for plan in updated["plans"]}) == 4
        assert all(plan["stTime"].endswith("14:00:00+08:00") for plan in updated["plans"])
        assert len(db.scalars(select(RemindEvt)).all()) == 8
    finally:
        db.close()


def test_day_view_contains_course_plan_but_not_course_template_or_reminders() -> None:
    db = _session()
    try:
        create_course_event(
            db,
            courseName="Physics",
            stTime="08:00",
            endTime="09:00",
            stDate="2026-09-07",
            endDate="2026-09-07",
            weekDay=1,
        )
        rows = list_events(
            db,
            date_value="2026-09-07",
            include_course_templates=False,
        )
        assert len(rows) == 1
        assert rows[0]["evtType"] == "plan"
        assert rows[0]["generatedBy"] == "course"
        assert rows[0]["courseName"] == "Physics"
    finally:
        db.close()


def test_time_range_query_handles_course_clock_fields() -> None:
    db = _session()
    try:
        create_course_event(
            db,
            courseName="Internship",
            stTime="10:00",
            endTime="19:00",
            stDate="2026-07-13",
            endDate="2026-08-14",
            weekDay=5,
        )
        rows = list_events(
            db,
            start="2026-07-17T00:00:00+08:00",
            end="2026-07-17T23:59:59+08:00",
        )
        assert {row["evtType"] for row in rows} == {"course", "plan"}
        assert any(row["evtType"] == "course" and row["title"] == "Internship" for row in rows)

        calendar_rows = list_events(
            db,
            start="2026-07-17T00:00:00+08:00",
            end="2026-07-17T23:59:59+08:00",
            include_course_templates=False,
        )
        assert len(calendar_rows) == 1
        assert calendar_rows[0]["evtType"] == "plan"
        assert calendar_rows[0]["title"] == "Internship"
    finally:
        db.close()
