from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.db import crud
from app.db.models import PendingOperation, PendingOperationStatus, Reminder, ReminderStatus


class ActionExecutor:
    def __init__(self, db: Session) -> None:
        self._db = db

    def confirm_and_apply(self, operation_id: int) -> PendingOperation:
        pending = self._get_pending_operation(operation_id)
        handlers = {
            "create_assignment": self._apply_create_assignment,
            "create_life_event": self._apply_create_life_event,
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
