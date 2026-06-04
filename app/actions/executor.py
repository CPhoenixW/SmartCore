from __future__ import annotations

from datetime import datetime

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
