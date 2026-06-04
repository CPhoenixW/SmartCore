from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import PendingOperation, PendingOperationStatus
from app.operations.parser import ParsedOperation


def create_pending_operation(db: Session, parsed: ParsedOperation) -> PendingOperation:
    pending = PendingOperation(
        source=parsed.source,
        raw_text=parsed.raw_text,
        action_name=parsed.action_name,
        operation_payload=parsed.payload,
        confidence=parsed.confidence,
        needs_confirmation=parsed.needs_confirmation,
        status=PendingOperationStatus.PENDING.value,
    )
    db.add(pending)
    db.commit()
    db.refresh(pending)
    return pending
