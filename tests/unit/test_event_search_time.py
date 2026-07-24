from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.server.db.session import Base
from app.server.new_core.course_semester import (
    create_course_event,
    expand_course_dates_from_semester,
    update_course_event,
)
from app.server.new_core.event_search import filter_events_by_text, normalize_search_query
from app.server.new_core.models import CoursePlan, RemindEvt

pytestmark = pytest.mark.unit


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return Session(engine)


def test_semester_start_and_week_numbers_define_course_dates() -> None:
    dates = expand_course_dates_from_semester(
        semester_start="2026-09-07",
        week_day="星期二",
        start_week=2,
        end_week=4,
        week_mode="all",
    )
    assert [item.isoformat() for item in dates] == [
        "2026-09-15",
        "2026-09-22",
        "2026-09-29",
    ]


def test_course_only_needs_semester_start_and_generates_relations() -> None:
    db = _session()
    try:
        course = create_course_event(
            db,
            courseName="Robotics",
            teacher="Teacher Wang",
            location="A101",
            semesterStart="2026-09-07",
            weekDay=2,
            stTime="08:00",
            endTime="09:40",
            startWeek=1,
            endWeek=3,
        )
        assert course["semesterStart"] == "2026-09-07"
        assert course["computedEndDate"] == "2026-09-22"
        assert [plan["occurrenceDate"] for plan in course["plans"]] == [
            "2026-09-08",
            "2026-09-15",
            "2026-09-22",
        ]
        assert len(db.scalars(select(CoursePlan)).all()) == 3
        assert len(db.scalars(select(RemindEvt)).all()) == 6
    finally:
        db.close()


def test_updating_week_order_recalculates_course_dates() -> None:
    db = _session()
    try:
        course = create_course_event(
            db,
            courseName="Math",
            semesterStart="2026-09-07",
            weekDay=1,
            stTime="10:00",
            endTime="11:30",
            startWeek=1,
            endWeek=4,
        )
        updated = update_course_event(
            db,
            course["evtId"],
            weekDay=4,
            startWeek=2,
            endWeek=4,
        )
        assert [plan["occurrenceDate"] for plan in updated["plans"]] == [
            "2026-09-17",
            "2026-09-24",
            "2026-10-01",
        ]
        assert len(db.scalars(select(RemindEvt)).all()) == 6
    finally:
        db.close()


def test_event_search_matches_date_weekday_and_clock_time() -> None:
    events = [
        {
            "evtId": "p1",
            "evtType": "plan",
            "title": "Robotics",
            "desc": "A101",
            "stTime": "2026-09-15T08:00:00+08:00",
            "durationMin": 100,
        }
    ]
    assert filter_events_by_text(events, "2026年9月15日") == events
    assert filter_events_by_text(events, "08:00") == events
    assert filter_events_by_text(events, "8点") == events
    assert filter_events_by_text(events, "星期二") == events
    assert filter_events_by_text(events, "2026/09/15 08:00") == events


def test_relative_date_search_is_replaced_not_appended() -> None:
    now = datetime(2026, 9, 14, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    assert normalize_search_query("明天 8点", now=now) == "2026-09-15 08:00"
