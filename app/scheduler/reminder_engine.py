from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session, joinedload

from app.actions.protocol import default_reminder_times, normalize_datetime
from app.db.models import (
    Assignment,
    AssignmentStatus,
    LifeEvent,
    LifeEventStatus,
    Reminder,
    ReminderStatus,
)
from app.scheduler.notification_cards import (
    build_daily_digest_card,
    build_ddl_card,
    build_event_reminder_card,
    build_pre_class_card,
    build_tomorrow_preview_card,
)
from app.secretary.assignments import get_assignments_due_on
from app.secretary.planner import build_today_plan, build_tomorrow_plan
from app.secretary.rules import DEFAULT_TZ, format_datetime
from app.secretary.timetable import get_course_instances_for_date


class NotificationSendError(Exception):
    """Raised when a notification cannot be delivered."""


@dataclass(frozen=True)
class OutboundNotification:
    dedup_key: str
    reminder_type: str
    target_type: str
    target_id: int | None
    scheduled_at: datetime
    card: dict[str, Any]
    fallback_text: str


class NotificationSender(Protocol):
    def send(
        self,
        *,
        card: dict[str, Any] | None = None,
        text: str = "",
    ) -> None:
        """Deliver a notification. Raise NotificationSendError on failure."""


REMINDER_DAILY_DIGEST = "daily_digest"
REMINDER_TOMORROW_PREVIEW = "tomorrow_preview"
REMINDER_PRE_CLASS = "pre_class"
REMINDER_DDL_EVE = "ddl_eve"
REMINDER_DDL_TODAY = "ddl_today"
REMINDER_ASSIGNMENT_PRE_DUE = "assignment_pre_due"
REMINDER_LIFE_EVENT = "life_event_pre_event"

TARGET_DAY = "day"
TARGET_COURSE_SESSION = "course_session"
TARGET_ASSIGNMENT = "assignment"
TARGET_LIFE_EVENT = "life_event"


@dataclass
class SchedulerConfig:
    morning_digest_time: time = time(7, 0)
    tomorrow_preview_time: time = time(21, 0)
    pre_class_lead_minutes: int = 15
    ddl_eve_time: time = time(20, 0)
    ddl_today_time: time = time(8, 0)
    tick_window_seconds: int = 60
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
    """Scan live schedule data each tick and send due notifications."""

    def __init__(self, config: SchedulerConfig | None = None) -> None:
        self.config = config or SchedulerConfig()

    def scan_and_notify(
        self,
        db: Session,
        sender: NotificationSender,
        *,
        now: datetime | None = None,
    ) -> int:
        current = self._normalize_now(now)
        due_items = self.collect_due_notifications(db, now=current)
        sent_count = 0
        for item in due_items:
            if self._dispatch_one(db, sender, item, current):
                sent_count += 1
        return sent_count

    def collect_due_notifications(
        self,
        db: Session,
        *,
        now: datetime | None = None,
    ) -> list[OutboundNotification]:
        current = self._normalize_now(now)
        candidates: list[OutboundNotification] = []
        candidates.extend(self._scan_daily_digest(db, current))
        candidates.extend(self._scan_tomorrow_preview(db, current))
        candidates.extend(self._scan_pre_class(db, current))
        candidates.extend(self._scan_ddl_reminders(db, current))
        candidates.extend(self._scan_assignment_pre_due(db, current))
        candidates.extend(self._scan_life_event_reminders(db, current))
        return [item for item in candidates if self._should_attempt_send(db, item.dedup_key)]

    def _normalize_now(self, now: datetime | None) -> datetime:
        current = now or datetime.now(self.config.tz)
        if current.tzinfo is None:
            return current.replace(tzinfo=self.config.tz)
        return current.astimezone(self.config.tz)

    def _is_due(self, scheduled_at: datetime, now: datetime) -> bool:
        window = timedelta(seconds=self.config.tick_window_seconds)
        return scheduled_at <= now < scheduled_at + window

    def _should_attempt_send(self, db: Session, dedup_key: str) -> bool:
        record = (
            db.query(Reminder)
            .filter(Reminder.dedup_key == dedup_key)
            .order_by(Reminder.id.desc())
            .first()
        )
        if record is None:
            return True
        if record.status == ReminderStatus.SENT.value:
            return False
        if record.status == ReminderStatus.FAILED.value:
            return record.retry_count < self.config.max_retries
        return True

    def _scan_daily_digest(self, db: Session, now: datetime) -> list[OutboundNotification]:
        today = now.date()
        scheduled_at = _combine_local(today, self.config.morning_digest_time, self.config.tz)
        if not self._is_due(scheduled_at, now):
            return []
        plan = build_today_plan(
            db,
            today=today,
            tz=self.config.tz,
            semester_start=self.config.semester_start,
        )
        card = build_daily_digest_card(plan)
        return [
            OutboundNotification(
                dedup_key=f"daily_digest:{today.isoformat()}",
                reminder_type=REMINDER_DAILY_DIGEST,
                target_type=TARGET_DAY,
                target_id=None,
                scheduled_at=scheduled_at,
                card=card,
                fallback_text=f"今日晨报 {today.isoformat()}",
            )
        ]

    def _scan_tomorrow_preview(self, db: Session, now: datetime) -> list[OutboundNotification]:
        today = now.date()
        scheduled_at = _combine_local(today, self.config.tomorrow_preview_time, self.config.tz)
        if not self._is_due(scheduled_at, now):
            return []
        plan = build_tomorrow_plan(
            db,
            today=today,
            tz=self.config.tz,
            semester_start=self.config.semester_start,
        )
        card = build_tomorrow_preview_card(plan)
        return [
            OutboundNotification(
                dedup_key=f"tomorrow_preview:{today.isoformat()}",
                reminder_type=REMINDER_TOMORROW_PREVIEW,
                target_type=TARGET_DAY,
                target_id=None,
                scheduled_at=scheduled_at,
                card=card,
                fallback_text=f"明日预告 {plan.target_date.isoformat()}",
            )
        ]

    def _scan_pre_class(self, db: Session, now: datetime) -> list[OutboundNotification]:
        today = now.date()
        items: list[OutboundNotification] = []
        for course in get_course_instances_for_date(
            db, today, semester_start=self.config.semester_start
        ):
            start = _parse_start_time(course.start_time)
            if start is None:
                continue
            start_dt = _combine_local(today, start, self.config.tz)
            scheduled_at = start_dt - timedelta(minutes=self.config.pre_class_lead_minutes)
            if not self._is_due(scheduled_at, now):
                continue
            minutes_until = max(
                1,
                int((start_dt - now).total_seconds() // 60),
            )
            card = build_pre_class_card(
                course_name=course.course_name,
                start_time=course.start_time,
                end_time=course.end_time,
                location=course.location,
                minutes_until=minutes_until,
            )
            items.append(
                OutboundNotification(
                    dedup_key=f"pre_class:{course.session_id}:{today.isoformat()}",
                    reminder_type=REMINDER_PRE_CLASS,
                    target_type=TARGET_COURSE_SESSION,
                    target_id=course.session_id,
                    scheduled_at=scheduled_at,
                    card=card,
                    fallback_text=f"课前提醒：{course.course_name}",
                )
            )
        return items

    def _scan_ddl_reminders(self, db: Session, now: datetime) -> list[OutboundNotification]:
        today = now.date()
        tomorrow = today + timedelta(days=1)
        items: list[OutboundNotification] = []

        eve_at = _combine_local(today, self.config.ddl_eve_time, self.config.tz)
        if self._is_due(eve_at, now):
            assignments = (
                db.query(Assignment)
                .options(joinedload(Assignment.course))
                .filter(
                    Assignment.due_at.isnot(None),
                    Assignment.due_at >= datetime.combine(
                        tomorrow, time.min, tzinfo=self.config.tz
                    ),
                    Assignment.due_at
                    < datetime.combine(
                        tomorrow + timedelta(days=1),
                        time.min,
                        tzinfo=self.config.tz,
                    ),
                    Assignment.status.notin_(
                        [AssignmentStatus.DONE.value, AssignmentStatus.CANCELLED.value]
                    ),
                )
                .all()
            )
            for assignment in assignments:
                course_name = assignment.course.name if assignment.course else None
                card = build_ddl_card(
                    title=assignment.title,
                    due_label=format_datetime(assignment.due_at, self.config.tz),
                    kind="eve",
                    course_name=course_name,
                    notes=assignment.notes,
                )
                items.append(
                    OutboundNotification(
                        dedup_key=f"ddl_eve:{assignment.id}:{today.isoformat()}",
                        reminder_type=REMINDER_DDL_EVE,
                        target_type=TARGET_ASSIGNMENT,
                        target_id=assignment.id,
                        scheduled_at=eve_at,
                        card=card,
                        fallback_text=f"DDL 提醒：{assignment.title}",
                    )
                )

        today_at = _combine_local(today, self.config.ddl_today_time, self.config.tz)
        if self._is_due(today_at, now):
            for assignment in get_assignments_due_on(db, today, self.config.tz):
                course_name = assignment.course.name if assignment.course else None
                card = build_ddl_card(
                    title=assignment.title,
                    due_label=format_datetime(assignment.due_at, self.config.tz),
                    kind="today",
                    course_name=course_name,
                    notes=assignment.notes,
                )
                items.append(
                    OutboundNotification(
                        dedup_key=f"ddl_today:{assignment.id}:{today.isoformat()}",
                        reminder_type=REMINDER_DDL_TODAY,
                        target_type=TARGET_ASSIGNMENT,
                        target_id=assignment.id,
                        scheduled_at=today_at,
                        card=card,
                        fallback_text=f"DDL 今日截止：{assignment.title}",
                    )
                )
        return items

    def _scan_assignment_pre_due(self, db: Session, now: datetime) -> list[OutboundNotification]:
        items: list[OutboundNotification] = []
        assignments = (
            db.query(Assignment)
            .options(joinedload(Assignment.course))
            .filter(
                Assignment.due_at.isnot(None),
                Assignment.status.notin_(
                    [AssignmentStatus.DONE.value, AssignmentStatus.CANCELLED.value]
                ),
            )
            .all()
        )
        for assignment in assignments:
            due_at = normalize_datetime(assignment.due_at)
            if due_at is None:
                continue
            for reminder_at in default_reminder_times(due_at):
                if not self._is_due(reminder_at, now):
                    continue
                course_name = assignment.course.name if assignment.course else None
                card = build_ddl_card(
                    title=assignment.title,
                    due_label=format_datetime(due_at, self.config.tz),
                    kind="today",
                    course_name=course_name,
                    notes=assignment.notes,
                )
                card["header"]["title"]["content"] = "作业截止提醒"
                items.append(
                    OutboundNotification(
                        dedup_key=(
                            f"assignment_pre_due:{assignment.id}:"
                            f"{reminder_at.isoformat()}"
                        ),
                        reminder_type=REMINDER_ASSIGNMENT_PRE_DUE,
                        target_type=TARGET_ASSIGNMENT,
                        target_id=assignment.id,
                        scheduled_at=reminder_at,
                        card=card,
                        fallback_text=f"作业提醒：{assignment.title}",
                    )
                )
        return items

    def _scan_life_event_reminders(self, db: Session, now: datetime) -> list[OutboundNotification]:
        items: list[OutboundNotification] = []
        events = (
            db.query(LifeEvent)
            .filter(
                LifeEvent.scheduled_at.isnot(None),
                LifeEvent.status.notin_(
                    [LifeEventStatus.DONE.value, LifeEventStatus.CANCELLED.value]
                ),
            )
            .all()
        )
        for event in events:
            scheduled_at = normalize_datetime(event.scheduled_at)
            if scheduled_at is None:
                continue
            for reminder_at in default_reminder_times(scheduled_at):
                if not self._is_due(reminder_at, now):
                    continue
                minutes_until = max(1, int((scheduled_at - now).total_seconds() // 60))
                card = build_event_reminder_card(
                    title=event.title,
                    event_type="schedule",
                    scheduled_label=format_datetime(scheduled_at, self.config.tz),
                    minutes_until=minutes_until,
                    notes=event.notes,
                )
                items.append(
                    OutboundNotification(
                        dedup_key=(
                            f"life_event_pre:{event.id}:{reminder_at.isoformat()}"
                        ),
                        reminder_type=REMINDER_LIFE_EVENT,
                        target_type=TARGET_LIFE_EVENT,
                        target_id=event.id,
                        scheduled_at=reminder_at,
                        card=card,
                        fallback_text=f"事项提醒：{event.title}",
                    )
                )
        return items

    def _dispatch_one(
        self,
        db: Session,
        sender: NotificationSender,
        item: OutboundNotification,
        now: datetime,
    ) -> bool:
        record = (
            db.query(Reminder)
            .filter(Reminder.dedup_key == item.dedup_key)
            .order_by(Reminder.id.desc())
            .first()
        )
        try:
            sender.send(card=item.card, text=item.fallback_text)
        except NotificationSendError:
            if record is None:
                record = Reminder(
                    dedup_key=item.dedup_key,
                    reminder_type=item.reminder_type,
                    target_type=item.target_type,
                    target_id=item.target_id,
                    scheduled_at=item.scheduled_at,
                    status=ReminderStatus.FAILED.value,
                    content=item.fallback_text,
                )
                db.add(record)
            record.retry_count += 1
            record.status = ReminderStatus.FAILED.value
            db.commit()
            return False

        if record is None:
            record = Reminder(
                dedup_key=item.dedup_key,
                reminder_type=item.reminder_type,
                target_type=item.target_type,
                target_id=item.target_id,
                scheduled_at=item.scheduled_at,
                status=ReminderStatus.SENT.value,
                content=item.fallback_text,
                sent_at=now,
            )
            db.add(record)
        else:
            record.status = ReminderStatus.SENT.value
            record.sent_at = now
            record.content = item.fallback_text
            record.retry_count = 0
        db.commit()
        return True
