from __future__ import annotations

from datetime import date, datetime

import pytest

from app.db import crud
from app.db.models import ReminderStatus, WeekRule
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
        self.cards: list[dict] = []
        self.fail_times = fail_times
        self.attempts = 0

    def send(self, *, card=None, text: str = "") -> None:
        self.attempts += 1
        if self.attempts <= self.fail_times:
            raise NotificationSendError("send failed")
        self.messages.append(text)
        if card is not None:
            self.cards.append(card)


def test_duplicate_scan_does_not_send_twice(db_session, engine, sample_course):
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

    sender = RecordingSender()
    now = datetime(2026, 3, 2, 7, 0, tzinfo=DEFAULT_TZ)
    first = engine.scan_and_notify(db_session, sender, now=now)
    second = engine.scan_and_notify(db_session, sender, now=now)

    assert first > 0
    assert second == 0
    assert len(sender.messages) == first


def test_scan_collects_all_reminder_types(db_session, engine, sample_course):
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

    morning = datetime(2026, 3, 2, 7, 0, tzinfo=DEFAULT_TZ)
    pre_class = datetime(2026, 3, 2, 7, 45, tzinfo=DEFAULT_TZ)
    ddl_today = datetime(2026, 3, 2, 8, 0, tzinfo=DEFAULT_TZ)
    ddl_eve = datetime(2026, 3, 2, 20, 0, tzinfo=DEFAULT_TZ)
    tomorrow_preview = datetime(2026, 3, 2, 21, 0, tzinfo=DEFAULT_TZ)

    collected_types = set()
    for moment in (morning, pre_class, ddl_today, ddl_eve, tomorrow_preview):
        for item in engine.collect_due_notifications(db_session, now=moment):
            collected_types.add(item.reminder_type)

    assert collected_types == {
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
        dedup_key="daily_digest:2026-03-02",
    )

    sender = RecordingSender()
    now = datetime(2026, 3, 2, 7, 0, tzinfo=DEFAULT_TZ)
    sent = engine.scan_and_notify(db_session, sender, now=now)

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
        dedup_key="daily_digest:2026-03-02",
        status=ReminderStatus.FAILED,
    )
    reminder.retry_count = 0
    db_session.commit()

    sender = RecordingSender(fail_times=1)
    now = datetime(2026, 3, 2, 7, 0, tzinfo=DEFAULT_TZ)
    engine.scan_and_notify(db_session, sender, now=now)

    db_session.refresh(reminder)
    assert reminder.retry_count == 1
    assert reminder.status == ReminderStatus.FAILED.value


def test_max_retries_marks_reminder_failed(db_session, engine):
    scheduled_at = datetime(2026, 3, 2, 7, 0, tzinfo=DEFAULT_TZ)
    reminder = crud.create_reminder(
        db_session,
        reminder_type=REMINDER_DAILY_DIGEST,
        target_type="day",
        scheduled_at=scheduled_at,
        content="digest",
        dedup_key="daily_digest:2026-03-02",
        status=ReminderStatus.FAILED,
    )
    reminder.retry_count = 0
    db_session.commit()

    sender = RecordingSender(fail_times=10)
    now = datetime(2026, 3, 2, 7, 0, tzinfo=DEFAULT_TZ)
    for _ in range(engine.config.max_retries):
        engine.scan_and_notify(db_session, sender, now=now)

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

    sender = RecordingSender()
    restarted_engine = ReminderEngine(scheduler_config)
    dispatch_at = datetime(2026, 3, 2, 21, 0, tzinfo=DEFAULT_TZ)
    sent = restarted_engine.scan_and_notify(db_session, sender, now=dispatch_at)

    assert sent > 0
    assert len(sender.messages) == sent


def test_runner_tick_scans_and_dispatches(db_session, scheduler_config, sample_course):
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
    now = datetime(2026, 3, 2, 21, 0, tzinfo=DEFAULT_TZ)
    sent = runner.tick(now=now)

    assert sent > 0
    assert sender.messages


def test_cancelled_dedup_record_does_not_block_rescan(db_session, engine):
    scheduled_at = datetime(2026, 3, 2, 7, 0, tzinfo=DEFAULT_TZ)
    crud.create_reminder(
        db_session,
        reminder_type=REMINDER_DAILY_DIGEST,
        target_type="day",
        scheduled_at=scheduled_at,
        content="cancelled",
        status=ReminderStatus.CANCELLED,
        dedup_key="daily_digest:2026-03-02",
    )

    sender = RecordingSender()
    now = datetime(2026, 3, 2, 7, 0, tzinfo=DEFAULT_TZ)
    sent = engine.scan_and_notify(db_session, sender, now=now)

    assert sent == 1
    assert sender.messages
