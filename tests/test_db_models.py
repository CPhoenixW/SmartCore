from datetime import UTC, datetime

from app.config import get_settings
from app.db import crud
from app.db.models import WeekRule


def test_creates_course(db_session):
    course = crud.create_course(db_session, name="Linear Algebra", teacher="Dr. Smith")
    assert course.id is not None
    assert course.name == "Linear Algebra"
    assert course.teacher == "Dr. Smith"


def test_creates_course_session(db_session):
    course = crud.create_course(db_session, name="Physics")
    session = crud.create_course_session(
        db_session,
        course_id=course.id,
        weekday=1,
        start_time="08:00",
        end_time="09:40",
        week_rule=WeekRule.ODD,
    )
    assert session.id is not None
    assert session.course_id == course.id
    assert session.weekday == 1
    assert session.week_rule == WeekRule.ODD.value


def test_creates_assignment_and_life_event(db_session):
    assignment = crud.create_assignment(
        db_session,
        title="Problem Set 3",
        notes="Chapter 5",
    )
    event = crud.create_life_event(db_session, title="Buy groceries")
    assert assignment.title == "Problem Set 3"
    assert event.title == "Buy groceries"


def test_creates_reminder(db_session):
    reminder = crud.create_reminder(
        db_session,
        reminder_type="ddl",
        target_type="assignment",
        scheduled_at=datetime(2026, 5, 30, 9, 0, tzinfo=UTC),
        content="DDL tomorrow",
    )
    assert reminder.status == "pending"
    assert reminder.retry_count == 0


def test_creates_message_log(db_session):
    log = crud.create_message_log(
        db_session,
        source="feishu",
        external_message_id="msg-001",
        raw_content="今日",
        parsed_command="today",
        reply_status="ok",
    )
    assert log.id is not None
    assert log.source == "feishu"
    assert log.parsed_command == "today"


def test_init_db_creates_all_tables(db_session):
    from sqlalchemy import inspect

    tables = set(inspect(db_session.get_bind()).get_table_names())
    assert tables == {
        "assignments",
        "course_sessions",
        "courses",
        "life_events",
        "message_logs",
        "reminders",
    }


def test_does_not_write_real_database(db_session, tmp_path):
    crud.create_course(db_session, name="Isolated Course")
    real_path = get_settings().database_path
    assert str(real_path).startswith(str(tmp_path))
    assert real_path.name == "test.sqlite"
