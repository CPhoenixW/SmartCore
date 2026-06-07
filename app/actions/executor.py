from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.db import crud
from app.db.models import (
    Assignment,
    AssignmentStatus,
    Course,
    CourseSession,
    LifeEvent,
    LifeEventStatus,
    PendingOperation,
    PendingOperationStatus,
    Reminder,
    ReminderStatus,
)
from app.secretary.rules import DEFAULT_TZ


class ActionExecutor:
    def __init__(self, db: Session) -> None:
        self._db = db

    def confirm_and_apply(self, operation_id: int) -> PendingOperation:
        pending = self._get_pending_operation(operation_id)
        handlers = {
            "create_event": self._apply_create_event,
            "update_event": self._apply_update_event,
            "delete_event": self._apply_delete_event,
        }
        handler = handlers.get(pending.action_name)
        if handler is None:
            pending.status = PendingOperationStatus.FAILED.value
            pending.error_message = f"unsupported action: {pending.action_name}"
            self._db.commit()
            self._db.refresh(pending)
            return pending
        try:
            return handler(pending)
        except Exception as exc:
            pending.status = PendingOperationStatus.FAILED.value
            pending.error_message = str(exc)
            self._db.commit()
            self._db.refresh(pending)
            return pending

    def reject(self, operation_id: int) -> PendingOperation:
        pending = self._get_pending_operation(operation_id)
        pending.status = PendingOperationStatus.REJECTED.value
        self._db.commit()
        self._db.refresh(pending)
        return pending

    def _get_pending_operation(self, operation_id: int) -> PendingOperation:
        pending = self._db.get(PendingOperation, operation_id)
        if pending is None:
            raise ValueError(f"pending operation not found: {operation_id}")
        if pending.status != PendingOperationStatus.PENDING.value:
            raise ValueError(f"operation {operation_id} is not pending")
        return pending

    def _create_life_event_from_fields(
        self,
        pending: PendingOperation,
        fields: dict,
    ) -> PendingOperation:
        title = fields.get("title")
        if not title:
            pending.status = PendingOperationStatus.FAILED.value
            pending.error_message = "missing life event title"
            self._db.commit()
            self._db.refresh(pending)
            return pending

        scheduled_at: datetime | None = None
        raw_scheduled_at = fields.get("scheduled_at")
        if raw_scheduled_at:
            scheduled_at = datetime.fromisoformat(raw_scheduled_at)

        deadline_at: datetime | None = None
        raw_deadline_at = fields.get("deadline_at")
        if raw_deadline_at:
            deadline_at = datetime.fromisoformat(raw_deadline_at)

        reminder_rule = fields.get("reminder_rule")
        notes = fields.get("notes")

        event = crud.create_life_event(
            self._db,
            title=title,
            scheduled_at=scheduled_at,
            deadline_at=deadline_at,
            reminder_rule=reminder_rule if isinstance(reminder_rule, str) else None,
            notes=notes if isinstance(notes, str) else None,
        )
        if scheduled_at is not None:
            lead_minutes = 15
            raw_lead = fields.get("reminder_lead_minutes")
            if raw_lead is not None:
                lead_minutes = int(raw_lead)
            try:
                crud.create_reminder(
                    self._db,
                    reminder_type="life_event_pre_event",
                    target_type="life_event",
                    target_id=event.id,
                    scheduled_at=scheduled_at - timedelta(minutes=lead_minutes),
                    content=f"提醒：{title}",
                )
            except Exception as exc:
                self._db.delete(event)
                pending.status = PendingOperationStatus.FAILED.value
                pending.error_message = str(exc)
                self._db.commit()
                self._db.refresh(pending)
                return pending
        pending.status = PendingOperationStatus.APPLIED.value
        pending.result_resource_type = "life_event"
        pending.result_resource_id = event.id
        pending.error_message = None
        self._db.commit()
        self._db.refresh(pending)
        return pending

    def query_events(self, payload: dict) -> list[dict]:
        selector = payload.get("selector") or {}
        fields = payload.get("fields") or {}
        event_type = selector.get("event_type") or fields.get("event_type", "all")
        status_filter = selector.get("status") or fields.get("status", "open")
        raw_max = selector.get("max_candidates") or fields.get("max_candidates") or 20
        max_candidates = min(int(raw_max), 50)
        time_range = selector.get("time_range") or fields.get("time_range")
        range_start, range_end = self._parse_time_range(time_range)
        results: list[dict] = []

        if event_type in ("all", "assignment"):
            query = self._db.query(Assignment)
            if status_filter == "open":
                query = query.filter(
                    Assignment.status.notin_(
                        [AssignmentStatus.DONE.value, AssignmentStatus.CANCELLED.value]
                    )
                )
            for item in query.all():
                if range_start is not None or range_end is not None:
                    if not self._datetime_in_range(item.due_at, range_start, range_end):
                        continue
                results.append(self._compact_assignment(item))

        if event_type in ("all", "life_event"):
            query = self._db.query(LifeEvent)
            if status_filter == "open":
                query = query.filter(
                    LifeEvent.status.notin_(
                        [LifeEventStatus.DONE.value, LifeEventStatus.CANCELLED.value]
                    )
                )
            for item in query.all():
                if range_start is not None or range_end is not None:
                    if not self._life_event_in_time_range(
                        item, range_start, range_end
                    ):
                        continue
                results.append(self._compact_life_event(item))

        if event_type in ("all", "course_session"):
            for item in self._db.query(CourseSession).all():
                results.append(self._compact_course_session(item))

        return results[:max_candidates]

    @staticmethod
    def _parse_time_range(
        time_range: dict | None,
    ) -> tuple[datetime | None, datetime | None]:
        if not isinstance(time_range, dict):
            return None, None
        start_raw = time_range.get("start")
        end_raw = time_range.get("end")
        start = datetime.fromisoformat(start_raw) if start_raw else None
        end = datetime.fromisoformat(end_raw) if end_raw else None
        return start, end

    @staticmethod
    def _normalize_datetime(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=DEFAULT_TZ)
        return value

    def _datetime_in_range(
        self,
        value: datetime | None,
        range_start: datetime | None,
        range_end: datetime | None,
    ) -> bool:
        dt = self._normalize_datetime(value)
        if dt is None:
            return False
        if range_start is not None:
            start = self._normalize_datetime(range_start)
            if start is not None and dt < start:
                return False
        if range_end is not None:
            end = self._normalize_datetime(range_end)
            if end is not None and dt >= end:
                return False
        return True

    def _life_event_in_time_range(
        self,
        event: LifeEvent,
        range_start: datetime | None,
        range_end: datetime | None,
    ) -> bool:
        for attr in ("scheduled_at", "deadline_at"):
            if self._datetime_in_range(getattr(event, attr), range_start, range_end):
                return True
        return False

    @staticmethod
    def _format_time_label(value: datetime | None) -> str:
        dt = ActionExecutor._normalize_datetime(value)
        if dt is None:
            return ""
        return dt.strftime("%Y-%m-%d %H:%M")

    @classmethod
    def _compact_assignment(cls, item: Assignment) -> dict:
        return {
            "event_type": "assignment",
            "id": item.id,
            "status": item.status,
            "time_label": cls._format_time_label(item.due_at),
            "title": item.title,
        }

    @classmethod
    def _compact_life_event(cls, item: LifeEvent) -> dict:
        time_source = item.scheduled_at or item.deadline_at
        return {
            "event_type": "life_event",
            "id": item.id,
            "status": item.status,
            "time_label": cls._format_time_label(time_source),
            "title": item.title,
        }

    @classmethod
    def _compact_course_session(cls, item: CourseSession) -> dict:
        return {
            "event_type": "course_session",
            "id": item.id,
            "status": "active",
            "time_label": "",
            "title": item.course.name if item.course else "",
        }

    def _apply_create_event(self, pending: PendingOperation) -> PendingOperation:
        fields = pending.operation_payload.get("fields") or {}
        event_type = fields.get("event_type")
        if event_type == "assignment":
            return self._create_event_assignment(pending, fields)
        if event_type == "life_event":
            return self._create_event_life_event(pending, fields)
        if event_type == "course_session":
            return self._create_event_course_session(pending, fields)
        pending.status = PendingOperationStatus.FAILED.value
        pending.error_message = f"unsupported event_type: {event_type}"
        self._db.commit()
        self._db.refresh(pending)
        return pending

    def _create_event_assignment(
        self, pending: PendingOperation, fields: dict
    ) -> PendingOperation:
        title = fields.get("title")
        if not title:
            pending.status = PendingOperationStatus.FAILED.value
            pending.error_message = "missing assignment title"
            self._db.commit()
            self._db.refresh(pending)
            return pending

        due_at: datetime | None = None
        raw_due_at = fields.get("due_at")
        if raw_due_at:
            due_at = datetime.fromisoformat(raw_due_at)

        assignment = crud.create_assignment(self._db, title=title, due_at=due_at)
        pending.status = PendingOperationStatus.APPLIED.value
        pending.result_resource_type = "assignment"
        pending.result_resource_id = assignment.id
        pending.error_message = None
        self._db.commit()
        self._db.refresh(pending)
        return pending

    def _create_event_life_event(
        self, pending: PendingOperation, fields: dict
    ) -> PendingOperation:
        life_fields = {k: v for k, v in fields.items() if k != "event_type"}
        return self._create_life_event_from_fields(pending, life_fields)

    def _create_event_course_session(
        self, pending: PendingOperation, fields: dict
    ) -> PendingOperation:
        course_name = fields.get("course_name")
        if not course_name:
            pending.status = PendingOperationStatus.FAILED.value
            pending.error_message = "missing course_name"
            self._db.commit()
            self._db.refresh(pending)
            return pending

        course = self._db.query(Course).filter(Course.name == course_name).first()
        if course is None:
            course = crud.create_course(
                self._db,
                name=course_name,
                teacher=fields.get("teacher") if isinstance(fields.get("teacher"), str) else None,
            )

        weekday = fields.get("weekday")
        if weekday is None:
            pending.status = PendingOperationStatus.FAILED.value
            pending.error_message = "missing weekday"
            self._db.commit()
            self._db.refresh(pending)
            return pending

        start_time = fields.get("start_time")
        end_time = fields.get("end_time")
        location = fields.get("location")
        session = crud.create_course_session(
            self._db,
            course_id=course.id,
            weekday=int(weekday),
            start_time=start_time if isinstance(start_time, str) else None,
            end_time=end_time if isinstance(end_time, str) else None,
            location_override=location if isinstance(location, str) else None,
        )
        pending.status = PendingOperationStatus.APPLIED.value
        pending.result_resource_type = "course_session"
        pending.result_resource_id = session.id
        pending.error_message = None
        self._db.commit()
        self._db.refresh(pending)
        return pending

    def _apply_update_event(self, pending: PendingOperation) -> PendingOperation:
        selector = pending.operation_payload.get("selector") or {}
        fields = pending.operation_payload.get("fields") or {}
        event_type = selector.get("event_type") or fields.get("event_type")
        resource_id = selector.get("id")

        if resource_id is None:
            pending.status = PendingOperationStatus.FAILED.value
            pending.error_message = "missing event id"
            self._db.commit()
            self._db.refresh(pending)
            return pending

        if event_type == "life_event":
            event = self._db.get(LifeEvent, resource_id)
            if event is None:
                pending.status = PendingOperationStatus.FAILED.value
                pending.error_message = f"life_event not found: {resource_id}"
                self._db.commit()
                self._db.refresh(pending)
                return pending

            if "title" in fields:
                event.title = fields["title"]
            if fields.get("scheduled_at"):
                event.scheduled_at = datetime.fromisoformat(fields["scheduled_at"])
                self._reschedule_life_event_reminders(event, fields)
            if fields.get("deadline_at"):
                event.deadline_at = datetime.fromisoformat(fields["deadline_at"])
            if "notes" in fields:
                event.notes = fields["notes"]

            pending.status = PendingOperationStatus.APPLIED.value
            pending.result_resource_type = "life_event"
            pending.result_resource_id = event.id
            pending.error_message = None
            self._db.commit()
            self._db.refresh(pending)
            return pending

        if event_type == "assignment":
            assignment = self._db.get(Assignment, resource_id)
            if assignment is None:
                pending.status = PendingOperationStatus.FAILED.value
                pending.error_message = f"assignment not found: {resource_id}"
                self._db.commit()
                self._db.refresh(pending)
                return pending

            if "title" in fields:
                assignment.title = fields["title"]
            if fields.get("due_at"):
                assignment.due_at = datetime.fromisoformat(fields["due_at"])
            if "notes" in fields:
                assignment.notes = fields["notes"]

            pending.status = PendingOperationStatus.APPLIED.value
            pending.result_resource_type = "assignment"
            pending.result_resource_id = assignment.id
            pending.error_message = None
            self._db.commit()
            self._db.refresh(pending)
            return pending

        if event_type == "course_session":
            session = self._db.get(CourseSession, resource_id)
            if session is None:
                pending.status = PendingOperationStatus.FAILED.value
                pending.error_message = f"course_session not found: {resource_id}"
                self._db.commit()
                self._db.refresh(pending)
                return pending

            if "weekday" in fields:
                session.weekday = int(fields["weekday"])
            if "start_time" in fields:
                session.start_time = fields["start_time"]
            if "end_time" in fields:
                session.end_time = fields["end_time"]
            if "location" in fields:
                session.location_override = fields["location"]

            pending.status = PendingOperationStatus.APPLIED.value
            pending.result_resource_type = "course_session"
            pending.result_resource_id = session.id
            pending.error_message = None
            self._db.commit()
            self._db.refresh(pending)
            return pending

        pending.status = PendingOperationStatus.FAILED.value
        pending.error_message = f"unsupported event_type for update: {event_type}"
        self._db.commit()
        self._db.refresh(pending)
        return pending

    def _reschedule_life_event_reminders(
        self,
        event: LifeEvent,
        fields: dict,
    ) -> None:
        if event.scheduled_at is None:
            return

        lead_minutes = 15
        raw_lead = fields.get("reminder_lead_minutes")
        if raw_lead is not None:
            lead_minutes = int(raw_lead)
        scheduled_at = event.scheduled_at - timedelta(minutes=lead_minutes)
        content = f"提醒：{event.title}"
        reminders = (
            self._db.query(Reminder)
            .filter(
                Reminder.reminder_type == "life_event_pre_event",
                Reminder.target_type == "life_event",
                Reminder.target_id == event.id,
                Reminder.status.in_(
                    [ReminderStatus.PENDING.value, ReminderStatus.FAILED.value]
                ),
            )
            .all()
        )
        if not reminders:
            crud.create_reminder(
                self._db,
                reminder_type="life_event_pre_event",
                target_type="life_event",
                target_id=event.id,
                scheduled_at=scheduled_at,
                content=content,
            )
            return
        for reminder in reminders:
            reminder.scheduled_at = scheduled_at
            reminder.content = content
            reminder.retry_count = 0
            reminder.status = ReminderStatus.PENDING.value

    def _apply_delete_event(self, pending: PendingOperation) -> PendingOperation:
        selector = pending.operation_payload.get("selector") or {}
        targets = selector.get("targets")
        if isinstance(targets, list) and targets:
            return self._apply_delete_event_targets(pending, targets)

        event_type = selector.get("event_type")
        resource_id = selector.get("id")

        if resource_id is None:
            pending.status = PendingOperationStatus.FAILED.value
            pending.error_message = "missing event id"
            self._db.commit()
            self._db.refresh(pending)
            return pending

        if event_type == "assignment":
            assignment = self._db.get(Assignment, resource_id)
            if assignment is None:
                pending.status = PendingOperationStatus.FAILED.value
                pending.error_message = f"assignment not found: {resource_id}"
                self._db.commit()
                self._db.refresh(pending)
                return pending
            assignment.status = AssignmentStatus.CANCELLED.value
            pending.status = PendingOperationStatus.APPLIED.value
            pending.result_resource_type = "assignment"
            pending.result_resource_id = assignment.id
            pending.error_message = None
            self._db.commit()
            self._db.refresh(pending)
            return pending

        if event_type == "life_event":
            event = self._db.get(LifeEvent, resource_id)
            if event is None:
                pending.status = PendingOperationStatus.FAILED.value
                pending.error_message = f"life_event not found: {resource_id}"
                self._db.commit()
                self._db.refresh(pending)
                return pending
            event.status = LifeEventStatus.CANCELLED.value
            pending.status = PendingOperationStatus.APPLIED.value
            pending.result_resource_type = "life_event"
            pending.result_resource_id = event.id
            pending.error_message = None
            self._db.commit()
            self._db.refresh(pending)
            return pending

        if event_type == "course_session":
            session = self._db.get(CourseSession, resource_id)
            if session is None:
                pending.status = PendingOperationStatus.FAILED.value
                pending.error_message = f"course_session not found: {resource_id}"
                self._db.commit()
                self._db.refresh(pending)
                return pending

            session_id = session.id
            self._db.delete(session)
            pending.status = PendingOperationStatus.APPLIED.value
            pending.result_resource_type = "course_session"
            pending.result_resource_id = session_id
            pending.error_message = None
            self._db.commit()
            self._db.refresh(pending)
            return pending

        pending.status = PendingOperationStatus.FAILED.value
        pending.error_message = f"unsupported event_type for delete: {event_type}"
        self._db.commit()
        self._db.refresh(pending)
        return pending

    def _apply_delete_event_targets(
        self,
        pending: PendingOperation,
        targets: list,
    ) -> PendingOperation:
        normalized_targets: list[tuple[str, int]] = []
        for target in targets:
            if not isinstance(target, dict):
                pending.status = PendingOperationStatus.FAILED.value
                pending.error_message = "invalid delete target"
                self._db.commit()
                self._db.refresh(pending)
                return pending
            event_type = target.get("event_type")
            resource_id = target.get("id")
            if event_type not in ("assignment", "life_event", "course_session"):
                pending.status = PendingOperationStatus.FAILED.value
                pending.error_message = f"unsupported event_type for delete: {event_type!r}"
                self._db.commit()
                self._db.refresh(pending)
                return pending
            if resource_id is None:
                pending.status = PendingOperationStatus.FAILED.value
                pending.error_message = "missing event id in delete targets"
                self._db.commit()
                self._db.refresh(pending)
                return pending
            if self._get_delete_event(event_type, int(resource_id)) is None:
                pending.status = PendingOperationStatus.FAILED.value
                pending.error_message = f"{event_type} not found: {resource_id}"
                pending.result_resource_type = event_type
                pending.result_resource_id = int(resource_id)
                self._db.commit()
                self._db.refresh(pending)
                return pending
            normalized_targets.append((event_type, int(resource_id)))

        last_resource_type: str | None = None
        last_resource_id: int | None = None
        for event_type, resource_id in normalized_targets:
            applied = self._delete_single_event(event_type, resource_id)
            if applied is None:
                pending.status = PendingOperationStatus.FAILED.value
                pending.error_message = f"{event_type} not found: {resource_id}"
                pending.result_resource_type = event_type
                pending.result_resource_id = resource_id
                self._db.commit()
                self._db.refresh(pending)
                return pending
            last_resource_type, last_resource_id = applied

        pending.status = PendingOperationStatus.APPLIED.value
        pending.result_resource_type = last_resource_type
        pending.result_resource_id = last_resource_id
        pending.error_message = None
        self._db.commit()
        self._db.refresh(pending)
        return pending

    def _get_delete_event(self, event_type: str, resource_id: int):
        if event_type == "assignment":
            return self._db.get(Assignment, resource_id)
        if event_type == "life_event":
            return self._db.get(LifeEvent, resource_id)
        if event_type == "course_session":
            return self._db.get(CourseSession, resource_id)
        return None

    def _delete_single_event(
        self,
        event_type: str,
        resource_id: int,
    ) -> tuple[str, int] | None:
        if event_type == "assignment":
            assignment = self._get_delete_event(event_type, resource_id)
            if assignment is None:
                return None
            assignment.status = AssignmentStatus.CANCELLED.value
            return "assignment", assignment.id

        if event_type == "life_event":
            event = self._get_delete_event(event_type, resource_id)
            if event is None:
                return None
            event.status = LifeEventStatus.CANCELLED.value
            return "life_event", event.id

        if event_type == "course_session":
            session = self._get_delete_event(event_type, resource_id)
            if session is None:
                return None
            session_id = session.id
            self._db.delete(session)
            return "course_session", session_id

        return None
