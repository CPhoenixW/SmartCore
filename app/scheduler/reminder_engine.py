from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.db.models import Reminder, ReminderStatus
from app.scheduler.daily_digest import (
    format_daily_digest,
    format_ddl_message,
    format_pre_class_message,
    format_tomorrow_preview,
)
from app.secretary.assignments import get_assignments_due_on
from app.secretary.planner import build_today_plan, build_tomorrow_plan
from app.secretary.rules import DEFAULT_TZ, format_datetime
from app.secretary.timetable import get_course_instances_for_date


class NotificationSendError(Exception):
    """Raised when a notification cannot be delivered."""


class NotificationSender(Protocol):
    def send(self, content: str) -> None:
        """Deliver a notification. Raise NotificationSendError on failure."""


REMINDER_DAILY_DIGEST = "daily_digest"
REMINDER_TOMORROW_PREVIEW = "tomorrow_preview"
REMINDER_PRE_CLASS = "pre_class"
REMINDER_DDL_EVE = "ddl_eve"
REMINDER_DDL_TODAY = "ddl_today"

TARGET_DAY = "day"
TARGET_COURSE_SESSION = "course_session"
TARGET_ASSIGNMENT = "assignment"


@dataclass
class SchedulerConfig:
    morning_digest_time: time = time(7, 0)
    tomorrow_preview_time: time = time(21, 0)
    pre_class_lead_minutes: int = 15
    ddl_eve_time: time = time(20, 0)
    ddl_today_time: time = time(8, 0)
    max_retries: int = 3
    semester_start: date | None = None
    tz: ZoneInfo = DEFAULT_TZ


def _combine_local(day: date, clock: time, tz: ZoneInfo) -> datetime:
    return datetime.combine(day, clock, tzinfo=tz)


def _parse_start_time(start_time: str | None) -> time | None:
    if not start_time:
        return None
    hour, minute = start_time.split(":", 1)
    return time(int(hour), int(minute))


class ReminderEngine:
    def __init__(self, config: SchedulerConfig | None = None) -> None:
        self.config = config or SchedulerConfig()

    def generate_reminders(self, db: Session, *, now: datetime | None = None) -> int:
        current = now or datetime.now(self.config.tz)
        if current.tzinfo is None:
            current = current.replace(tzinfo=self.config.tz)
        else:
            current = current.astimezone(self.config.tz)

        today = current.date()
        created = 0
        created += self._generate_daily_digest(db, today)
        created += self._generate_tomorrow_preview(db, today)
        created += self._generate_pre_class_reminders(db, today)
        created += self._generate_ddl_reminders(db, today)
        return created

    def dispatch_due_reminders(
        self,
        db: Session,
        sender: NotificationSender,
        *,
        now: datetime | None = None,
    ) -> int:
        current = now or datetime.now(self.config.tz)
        if current.tzinfo is None:
            current = current.replace(tzinfo=self.config.tz)
        else:
            current = current.astimezone(self.config.tz)

        due_reminders = (
            db.query(Reminder)
            .filter(
                Reminder.status.in_(
                    [ReminderStatus.PENDING.value, ReminderStatus.FAILED.value]
                ),
                Reminder.scheduled_at <= current,
                Reminder.retry_count < self.config.max_retries,
            )
            .order_by(Reminder.scheduled_at.asc(), Reminder.id.asc())
            .all()
        )

        sent_count = 0
        for reminder in due_reminders:
            if reminder.status == ReminderStatus.SENT.value:
                continue
            if self._dispatch_one(db, sender, reminder, current):
                sent_count += 1
        return sent_count

    def cancel_reminders_for_target(
        self,
        db: Session,
        *,
        target_type: str,
        target_id: int,
    ) -> int:
        reminders = (
            db.query(Reminder)
            .filter(
                Reminder.target_type == target_type,
                Reminder.target_id == target_id,
                Reminder.status.in_(
                    [ReminderStatus.PENDING.value, ReminderStatus.FAILED.value]
                ),
            )
            .all()
        )
        for reminder in reminders:
            reminder.status = ReminderStatus.CANCELLED.value
        if reminders:
            db.commit()
        return len(reminders)

    def _generate_daily_digest(self, db: Session, today: date) -> int:
        scheduled_at = _combine_local(
            today, self.config.morning_digest_time, self.config.tz
        )
        plan = build_today_plan(
            db,
            today=today,
            tz=self.config.tz,
            semester_start=self.config.semester_start,
        )
        content = format_daily_digest(plan)
        return 1 if self._create_if_absent(
            db,
            reminder_type=REMINDER_DAILY_DIGEST,
            target_type=TARGET_DAY,
            target_id=None,
            scheduled_at=scheduled_at,
            content=content,
        ) else 0

    def _generate_tomorrow_preview(self, db: Session, today: date) -> int:
        scheduled_at = _combine_local(
            today, self.config.tomorrow_preview_time, self.config.tz
        )
        plan = build_tomorrow_plan(
            db,
            today=today,
            tz=self.config.tz,
            semester_start=self.config.semester_start,
        )
        content = format_tomorrow_preview(plan)
        return 1 if self._create_if_absent(
            db,
            reminder_type=REMINDER_TOMORROW_PREVIEW,
            target_type=TARGET_DAY,
            target_id=None,
            scheduled_at=scheduled_at,
            content=content,
        ) else 0

    def _generate_pre_class_reminders(self, db: Session, today: date) -> int:
        created = 0
        for course in get_course_instances_for_date(
            db, today, semester_start=self.config.semester_start
        ):
            start = _parse_start_time(course.start_time)
            if start is None:
                continue
            start_dt = _combine_local(today, start, self.config.tz)
            scheduled_at = start_dt - timedelta(minutes=self.config.pre_class_lead_minutes)
            content = format_pre_class_message(
                course_name=course.course_name,
                start_time=course.start_time,
                location=course.location,
            )
            if self._create_if_absent(
                db,
                reminder_type=REMINDER_PRE_CLASS,
                target_type=TARGET_COURSE_SESSION,
                target_id=course.session_id,
                scheduled_at=scheduled_at,
                content=content,
            ):
                created += 1
        return created

    def _generate_ddl_reminders(self, db: Session, today: date) -> int:
        created = 0
        tomorrow = today + timedelta(days=1)

        for assignment in get_assignments_due_on(db, tomorrow, self.config.tz):
            scheduled_at = _combine_local(today, self.config.ddl_eve_time, self.config.tz)
            content = format_ddl_message(
                title=assignment.title,
                due_label=format_datetime(assignment.due_at, self.config.tz),
                kind="eve",
            )
            if self._create_if_absent(
                db,
                reminder_type=REMINDER_DDL_EVE,
                target_type=TARGET_ASSIGNMENT,
                target_id=assignment.id,
                scheduled_at=scheduled_at,
                content=content,
            ):
                created += 1

        for assignment in get_assignments_due_on(db, today, self.config.tz):
            scheduled_at = _combine_local(today, self.config.ddl_today_time, self.config.tz)
            content = format_ddl_message(
                title=assignment.title,
                due_label=format_datetime(assignment.due_at, self.config.tz),
                kind="today",
            )
            if self._create_if_absent(
                db,
                reminder_type=REMINDER_DDL_TODAY,
                target_type=TARGET_ASSIGNMENT,
                target_id=assignment.id,
                scheduled_at=scheduled_at,
                content=content,
            ):
                created += 1

        return created

    def _find_existing(
        self,
        db: Session,
        *,
        reminder_type: str,
        target_type: str,
        target_id: int | None,
        scheduled_at: datetime,
    ) -> Reminder | None:
        query = db.query(Reminder).filter(
            Reminder.reminder_type == reminder_type,
            Reminder.target_type == target_type,
            Reminder.scheduled_at == scheduled_at,
        )
        if target_id is None:
            query = query.filter(Reminder.target_id.is_(None))
        else:
            query = query.filter(Reminder.target_id == target_id)
        return query.first()

    def _create_if_absent(
        self,
        db: Session,
        *,
        reminder_type: str,
        target_type: str,
        target_id: int | None,
        scheduled_at: datetime,
        content: str,
    ) -> bool:
        existing = self._find_existing(
            db,
            reminder_type=reminder_type,
            target_type=target_type,
            target_id=target_id,
            scheduled_at=scheduled_at,
        )
        if existing is not None:
            return False

        reminder = Reminder(
            reminder_type=reminder_type,
            target_type=target_type,
            target_id=target_id,
            scheduled_at=scheduled_at,
            status=ReminderStatus.PENDING.value,
            content=content,
        )
        db.add(reminder)
        db.commit()
        db.refresh(reminder)
        return True

    def _dispatch_one(
        self,
        db: Session,
        sender: NotificationSender,
        reminder: Reminder,
        now: datetime,
    ) -> bool:
        content = reminder.content or ""
        try:
            sender.send(content)
        except NotificationSendError:
            reminder.retry_count += 1
            if reminder.retry_count >= self.config.max_retries:
                reminder.status = ReminderStatus.FAILED.value
            else:
                reminder.status = ReminderStatus.PENDING.value
            db.commit()
            return False

        reminder.status = ReminderStatus.SENT.value
        reminder.sent_at = now
        db.commit()
        return True
