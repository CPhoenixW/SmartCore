from __future__ import annotations

from datetime import date, datetime

import pytest

from app.db import crud
from app.db.models import Reminder, ReminderStatus, WeekRule
from app.scheduler.reminder_engine import (
    REMINDER_DAILY_DIGEST,
    REMINDER_DDL_EVE,
    REMINDER_DDL_TODAY,
    REMINDER_PRE_CLASS,
    REMINDER_TOMORROW_PREVIEW,
    NotificationSendError,
    ReminderEngine,
    SchedulerConfig,
)
from app.scheduler.runner import SchedulerRunner
from app.secretary.rules import DEFAULT_TZ

SEMESTER_START = date(2026, 2, 23)
TODAY = date(2026, 3, 2)


@pytest.fixture
def scheduler_config():
    return SchedulerConfig(semester_start=SEMESTER_START, tz=DEFAULT_TZ, max_retries=3)


@pytest.fixture
def engine(scheduler_config):
    return ReminderEngine(scheduler_config)


@pytest.fixture
def sample_course(db_session):
    return crud.create_course(
        db_session,
        name="Algorithms",
        default_location="Room A101",
    )


class RecordingSender:
    def __init__(self, *, fail_times: int = 0):
        self.messages: list[str] = []
        self.fail_times = fail_times
        self.attempts = 0

    def send(self, content: str) -> None:
        self.attempts += 1
        if self.attempts <= self.fail_times:
            raise NotificationSendError("send failed")
        self.messages.append(content)


def test_duplicate_generation_does_not_create_reminders(db_session, engine, sample_course):
    crud.create_course_session(
        db_session,
        course_id=sample_course.id,
        weekday=1,
        start_time="08:00",
        end_time="09:40",
        week_rule=WeekRule.EVERY,
    )
    crud.create_assignment(
        db_session,
        title="Essay draft",
        due_at=datetime(2026, 3, 2, 23, 59, tzinfo=DEFAULT_TZ),
    )
    crud.create_assignment(
        db_session,
        title="Lab report",
        due_at=datetime(2026, 3, 3, 23, 59, tzinfo=DEFAULT_TZ),
    )

    now = datetime(2026, 3, 2, 6, 0, tzinfo=DEFAULT_TZ)
    first = engine.generate_reminders(db_session, now=now)
    second = engine.generate_reminders(db_session, now=now)

    assert first > 0
    assert second == 0
    assert db_session.query(Reminder).count() == first


def test_generates_all_reminder_types(db_session, engine, sample_course):
    crud.create_course_session(
        db_session,
        course_id=sample_course.id,
        weekday=1,
        start_time="08:00",
        end_time="09:40",
        week_rule=WeekRule.EVERY,
    )
    crud.create_assignment(
        db_session,
        title="Essay draft",
        due_at=datetime(2026, 3, 2, 23, 59, tzinfo=DEFAULT_TZ),
    )
    crud.create_assignment(
        db_session,
        title="Lab report",
        due_at=datetime(2026, 3, 3, 23, 59, tzinfo=DEFAULT_TZ),
    )

    now = datetime(2026, 3, 2, 6, 0, tzinfo=DEFAULT_TZ)
    engine.generate_reminders(db_session, now=now)

    types = {item.reminder_type for item in db_session.query(Reminder).all()}
    assert types == {
        REMINDER_DAILY_DIGEST,
        REMINDER_TOMORROW_PREVIEW,
        REMINDER_PRE_CLASS,
        REMINDER_DDL_EVE,
        REMINDER_DDL_TODAY,
    }


def test_sent_reminder_is_not_sent_again(db_session, engine):
    scheduled_at = datetime(2026, 3, 2, 7, 0, tzinfo=DEFAULT_TZ)
    crud.create_reminder(
        db_session,
        reminder_type=REMINDER_DAILY_DIGEST,
        target_type="day",
        scheduled_at=scheduled_at,
        content="already sent",
        status=ReminderStatus.SENT,
    )

    sender = RecordingSender()
    now = datetime(2026, 3, 2, 8, 0, tzinfo=DEFAULT_TZ)
    sent = engine.dispatch_due_reminders(db_session, sender, now=now)

    assert sent == 0
    assert sender.messages == []


def test_failed_send_increments_retry_count(db_session, engine):
    scheduled_at = datetime(2026, 3, 2, 7, 0, tzinfo=DEFAULT_TZ)
    reminder = crud.create_reminder(
        db_session,
        reminder_type=REMINDER_DAILY_DIGEST,
        target_type="day",
        scheduled_at=scheduled_at,
        content="digest",
    )

    sender = RecordingSender(fail_times=1)
    now = datetime(2026, 3, 2, 8, 0, tzinfo=DEFAULT_TZ)
    engine.dispatch_due_reminders(db_session, sender, now=now)

    db_session.refresh(reminder)
    assert reminder.retry_count == 1
    assert reminder.status == ReminderStatus.PENDING.value


def test_max_retries_marks_reminder_failed(db_session, engine):
    scheduled_at = datetime(2026, 3, 2, 7, 0, tzinfo=DEFAULT_TZ)
    reminder = crud.create_reminder(
        db_session,
        reminder_type=REMINDER_DAILY_DIGEST,
        target_type="day",
        scheduled_at=scheduled_at,
        content="digest",
    )

    sender = RecordingSender(fail_times=10)
    now = datetime(2026, 3, 2, 8, 0, tzinfo=DEFAULT_TZ)
    for _ in range(engine.config.max_retries):
        engine.dispatch_due_reminders(db_session, sender, now=now)

    db_session.refresh(reminder)
    assert reminder.retry_count == engine.config.max_retries
    assert reminder.status == ReminderStatus.FAILED.value


def test_pending_reminders_continue_after_restart(db_session, scheduler_config, sample_course):
    crud.create_course_session(
        db_session,
        course_id=sample_course.id,
        weekday=1,
        start_time="08:00",
        end_time="09:40",
        week_rule=WeekRule.EVERY,
    )

    now = datetime(2026, 3, 2, 6, 0, tzinfo=DEFAULT_TZ)
    first_engine = ReminderEngine(scheduler_config)
    first_engine.generate_reminders(db_session, now=now)

    pending_count = (
        db_session.query(Reminder)
        .filter(Reminder.status == ReminderStatus.PENDING.value)
        .count()
    )
    assert pending_count > 0

    sender = RecordingSender()
    restarted_engine = ReminderEngine(scheduler_config)
    dispatch_at = datetime(2026, 3, 2, 22, 0, tzinfo=DEFAULT_TZ)
    sent = restarted_engine.dispatch_due_reminders(db_session, sender, now=dispatch_at)

    assert sent > 0
    assert len(sender.messages) == sent


def test_runner_tick_generates_and_dispatches(db_session, scheduler_config, sample_course):
    crud.create_course_session(
        db_session,
        course_id=sample_course.id,
        weekday=1,
        start_time="08:00",
        end_time="09:40",
        week_rule=WeekRule.EVERY,
    )

    sender = RecordingSender()
    runner = SchedulerRunner(lambda: db_session, sender, scheduler_config)
    now = datetime(2026, 3, 2, 22, 0, tzinfo=DEFAULT_TZ)
    created, sent = runner.tick(now=now)

    assert created > 0
    assert sent > 0
    assert sender.messages


def test_cancelled_reminder_is_not_sent(db_session, engine):
    scheduled_at = datetime(2026, 3, 2, 7, 0, tzinfo=DEFAULT_TZ)
    crud.create_reminder(
        db_session,
        reminder_type=REMINDER_DAILY_DIGEST,
        target_type="day",
        scheduled_at=scheduled_at,
        content="cancelled",
        status=ReminderStatus.CANCELLED,
    )

    sender = RecordingSender()
    now = datetime(2026, 3, 2, 8, 0, tzinfo=DEFAULT_TZ)
    sent = engine.dispatch_due_reminders(db_session, sender, now=now)

    assert sent == 0
    assert sender.messages == []
