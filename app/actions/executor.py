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


class ActionExecutor:
    def __init__(self, db: Session) -> None:
        self._db = db

    def confirm_and_apply(self, operation_id: int) -> PendingOperation:
        pending = self._get_pending_operation(operation_id)
        handlers = {
            "create_assignment": self._apply_create_assignment,
            "create_life_event": self._apply_create_life_event,
            "create_event": self._apply_create_event,
            "update_event": self._apply_update_event,
            "delete_event": self._apply_delete_event,
            "update_reminder": self._apply_update_reminder,
            "cancel_reminder": self._apply_cancel_reminder,
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

    def _apply_create_assignment(self, pending: PendingOperation) -> PendingOperation:
        fields = pending.operation_payload.get("fields", {})
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

    def _apply_create_life_event(self, pending: PendingOperation) -> PendingOperation:
        fields = pending.operation_payload.get("fields", {})
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
        fields = payload.get("fields") or {}
        event_type = fields.get("event_type", "all")
        status_filter = fields.get("status", "open")
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
                results.append(
                    {
                        "id": item.id,
                        "event_type": "assignment",
                        "title": item.title,
                        "status": item.status,
                    }
                )

        if event_type in ("all", "life_event"):
            query = self._db.query(LifeEvent)
            if status_filter == "open":
                query = query.filter(
                    LifeEvent.status.notin_(
                        [LifeEventStatus.DONE.value, LifeEventStatus.CANCELLED.value]
                    )
                )
            for item in query.all():
                results.append(
                    {
                        "id": item.id,
                        "event_type": "life_event",
                        "title": item.title,
                        "status": item.status,
                    }
                )

        if event_type in ("all", "course_session"):
            for item in self._db.query(CourseSession).all():
                results.append(
                    {
                        "id": item.id,
                        "event_type": "course_session",
                        "title": item.course.name if item.course else "",
                        "status": "active",
                    }
                )

        return results

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
        pending.operation_payload = {
            **pending.operation_payload,
            "fields": life_fields,
        }
        return self._apply_create_life_event(pending)

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

    def _apply_delete_event(self, pending: PendingOperation) -> PendingOperation:
        selector = pending.operation_payload.get("selector") or {}
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

    def _apply_update_reminder(self, pending: PendingOperation) -> PendingOperation:
        selector = pending.operation_payload.get("selector") or {}
        reminder_id = selector.get("id")
        if reminder_id is None:
            pending.status = PendingOperationStatus.FAILED.value
            pending.error_message = "missing reminder id"
            self._db.commit()
            self._db.refresh(pending)
            return pending

        reminder = self._db.get(Reminder, reminder_id)
        if reminder is None:
            pending.status = PendingOperationStatus.FAILED.value
            pending.error_message = f"reminder not found: {reminder_id}"
            self._db.commit()
            self._db.refresh(pending)
            return pending

        if reminder.status != ReminderStatus.PENDING.value:
            pending.status = PendingOperationStatus.FAILED.value
            pending.error_message = (
                f"reminder #{reminder_id} cannot be updated in status {reminder.status}"
            )
            self._db.commit()
            self._db.refresh(pending)
            return pending

        fields = pending.operation_payload.get("fields") or {}
        raw_scheduled_at = fields.get("scheduled_at")
        if not raw_scheduled_at:
            pending.status = PendingOperationStatus.FAILED.value
            pending.error_message = "missing scheduled_at"
            self._db.commit()
            self._db.refresh(pending)
            return pending

        reminder.scheduled_at = datetime.fromisoformat(raw_scheduled_at)
        pending.status = PendingOperationStatus.APPLIED.value
        pending.result_resource_type = "reminder"
        pending.result_resource_id = reminder.id
        pending.error_message = None
        self._db.commit()
        self._db.refresh(pending)
        return pending

    def _apply_cancel_reminder(self, pending: PendingOperation) -> PendingOperation:
        selector = pending.operation_payload.get("selector") or {}
        reminder_id = selector.get("id")
        if reminder_id is None:
            pending.status = PendingOperationStatus.FAILED.value
            pending.error_message = "missing reminder id"
            self._db.commit()
            self._db.refresh(pending)
            return pending

        reminder = self._db.get(Reminder, reminder_id)
        if reminder is None:
            pending.status = PendingOperationStatus.FAILED.value
            pending.error_message = f"reminder not found: {reminder_id}"
            self._db.commit()
            self._db.refresh(pending)
            return pending

        if reminder.status == ReminderStatus.SENT.value:
            pending.status = PendingOperationStatus.FAILED.value
            pending.error_message = f"reminder #{reminder_id} already sent, cannot cancel"
            pending.result_resource_type = "reminder"
            pending.result_resource_id = reminder.id
            self._db.commit()
            self._db.refresh(pending)
            return pending

        if reminder.status not in (
            ReminderStatus.PENDING.value,
            ReminderStatus.FAILED.value,
        ):
            pending.status = PendingOperationStatus.FAILED.value
            pending.error_message = (
                f"reminder #{reminder_id} cannot be cancelled in status {reminder.status}"
            )
            self._db.commit()
            self._db.refresh(pending)
            return pending

        reminder.status = ReminderStatus.CANCELLED.value
        pending.status = PendingOperationStatus.APPLIED.value
        pending.result_resource_type = "reminder"
        pending.result_resource_id = reminder.id
        pending.error_message = None
        self._db.commit()
        self._db.refresh(pending)
        return pending
