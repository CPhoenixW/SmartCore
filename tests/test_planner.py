from datetime import date, datetime

import pytest

from app.db import crud
from app.db.models import WeekRule
from app.secretary.planner import build_today_plan, build_tomorrow_plan
from app.secretary.rules import DEFAULT_TZ
from app.secretary.timetable import get_course_instances_for_date, session_applies_on_date


SEMESTER_START = date(2026, 2, 23)


@pytest.fixture
def sample_course(db_session):
    course = crud.create_course(
        db_session,
        name="Algorithms",
        default_location="Room A101",
    )
    return course


def test_every_week_course(db_session, sample_course):
    crud.create_course_session(
        db_session,
        course_id=sample_course.id,
        weekday=1,
        start_time="08:00",
        end_time="09:40",
        week_rule=WeekRule.EVERY,
    )
    monday = date(2026, 3, 2)
    instances = get_course_instances_for_date(
        db_session, monday, semester_start=SEMESTER_START
    )
    assert len(instances) == 1
    assert instances[0].course_name == "Algorithms"
    assert instances[0].location == "Room A101"


def test_odd_week_course(db_session, sample_course):
    session = crud.create_course_session(
        db_session,
        course_id=sample_course.id,
        weekday=2,
        start_time="10:00",
        end_time="11:40",
        week_rule=WeekRule.ODD,
    )
    odd_tuesday = date(2026, 2, 24)
    even_tuesday = date(2026, 3, 3)
    assert session_applies_on_date(session, odd_tuesday, semester_start=SEMESTER_START)
    assert not session_applies_on_date(session, even_tuesday, semester_start=SEMESTER_START)


def test_week_range_course(db_session, sample_course):
    session = crud.create_course_session(
        db_session,
        course_id=sample_course.id,
        weekday=5,
        start_time="13:00",
        end_time="14:40",
        week_rule=WeekRule.RANGE,
        week_range="1-2",
    )
    week1_friday = date(2026, 2, 27)
    week2_friday = date(2026, 3, 6)
    week3_friday = date(2026, 3, 13)
    assert session_applies_on_date(session, week1_friday, semester_start=SEMESTER_START)
    assert session_applies_on_date(session, week2_friday, semester_start=SEMESTER_START)
    assert not session_applies_on_date(session, week3_friday, semester_start=SEMESTER_START)


def test_even_week_course(db_session, sample_course):
    session = crud.create_course_session(
        db_session,
        course_id=sample_course.id,
        weekday=3,
        start_time="14:00",
        end_time="15:40",
        week_rule=WeekRule.EVEN,
    )
    even_wednesday = date(2026, 3, 4)
    odd_wednesday = date(2026, 2, 25)
    assert session_applies_on_date(session, even_wednesday, semester_start=SEMESTER_START)
    assert not session_applies_on_date(session, odd_wednesday, semester_start=SEMESTER_START)


def test_location_override(db_session, sample_course):
    crud.create_course_session(
        db_session,
        course_id=sample_course.id,
        weekday=4,
        start_time="16:00",
        end_time="17:40",
        location_override="Lab B203",
    )
    thursday = date(2026, 2, 26)
    instances = get_course_instances_for_date(
        db_session, thursday, semester_start=SEMESTER_START
    )
    assert instances[0].location == "Lab B203"


def test_same_day_ddl_in_today_plan(db_session, sample_course):
    today = date(2026, 3, 2)
    crud.create_assignment(
        db_session,
        title="Essay draft",
        due_at=datetime(2026, 3, 2, 23, 59, tzinfo=DEFAULT_TZ),
    )
    plan = build_today_plan(
        db_session,
        today=today,
        tz=DEFAULT_TZ,
        semester_start=SEMESTER_START,
    )
    assert any(item.title == "Essay draft" for item in plan.assignments)


def test_tomorrow_courses_in_tomorrow_plan(db_session, sample_course):
    today = date(2026, 3, 2)
    crud.create_course_session(
        db_session,
        course_id=sample_course.id,
        weekday=2,
        start_time="08:00",
        end_time="09:40",
        week_rule=WeekRule.EVERY,
    )
    plan = build_tomorrow_plan(
        db_session,
        today=today,
        tz=DEFAULT_TZ,
        semester_start=SEMESTER_START,
    )
    assert plan.target_date == date(2026, 3, 3)
    assert any(item.title == "Algorithms" for item in plan.courses)


def test_unscheduled_life_event_in_today_plan(db_session):
    today = date(2026, 3, 2)
    crud.create_life_event(db_session, title="Call mom")
    plan = build_today_plan(
        db_session,
        today=today,
        tz=DEFAULT_TZ,
        semester_start=SEMESTER_START,
    )
    assert any(item.title == "Call mom" for item in plan.unscheduled)
