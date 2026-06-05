from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.db import crud
from app.db.models import PendingOperation, PendingOperationStatus


class ActionExecutor:
    def __init__(self, db: Session) -> None:
        self._db = db

    def confirm_and_apply(self, operation_id: int) -> PendingOperation:
        pending = self._get_pending_operation(operation_id)
        if pending.action_name == "create_assignment":
            return self._apply_create_assignment(pending)
        if pending.action_name == "create_life_event":
            return self._apply_create_life_event(pending)
        pending.status = PendingOperationStatus.FAILED.value
        pending.error_message = f"unsupported action: {pending.action_name}"
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
            crud.create_reminder(
                self._db,
                reminder_type="life_event_pre_event",
                target_type="life_event",
                target_id=event.id,
                scheduled_at=scheduled_at - timedelta(minutes=lead_minutes),
                content=f"提醒：{title}",
            )
        pending.status = PendingOperationStatus.APPLIED.value
        pending.result_resource_type = "life_event"
        pending.result_resource_id = event.id
        pending.error_message = None
        self._db.commit()
        self._db.refresh(pending)
        return pending
