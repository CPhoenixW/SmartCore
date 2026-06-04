from __future__ import annotations

from datetime import datetime

from app.actions.executor import ActionExecutor
from app.db.models import Assignment, PendingOperation, PendingOperationStatus
from app.operations.parser import RuleBasedOperationParser
from app.operations.store import create_pending_operation
from app.secretary.rules import DEFAULT_TZ


def test_rule_parser_creates_assignment_operation() -> None:
    parser = RuleBasedOperationParser(tz=DEFAULT_TZ)

    operation = parser.parse(
        "添加作业 高数作业 2026-06-10 20:00",
        source="feishu",
    )

    assert operation.source == "feishu"
    assert operation.raw_text == "添加作业 高数作业 2026-06-10 20:00"
    assert operation.action_name == "create_assignment"
    assert operation.needs_confirmation is True
    assert operation.confidence >= 0.9
    assert operation.payload == {
        "resource": "assignment",
        "fields": {
            "title": "高数作业",
            "due_at": "2026-06-10T20:00:00+08:00",
        },
    }


def test_pending_operation_confirm_executes_action(db_session) -> None:
    parser = RuleBasedOperationParser(tz=DEFAULT_TZ)
    parsed = parser.parse("添加作业 高数作业 2026-06-10 20:00", source="feishu")
    pending = create_pending_operation(db_session, parsed)

    assert pending.id is not None
    assert pending.status == PendingOperationStatus.PENDING.value

    executor = ActionExecutor(db_session)
    applied = executor.confirm_and_apply(pending.id)

    assignment = db_session.query(Assignment).filter_by(title="高数作业").one()
    expected_due_at = datetime(2026, 6, 10, 20, 0, tzinfo=DEFAULT_TZ)
    due_at = assignment.due_at
    if due_at is not None and due_at.tzinfo is None:
        due_at = due_at.replace(tzinfo=DEFAULT_TZ)
    assert due_at == expected_due_at

    db_session.refresh(applied)
    assert applied.status == PendingOperationStatus.APPLIED.value
    assert applied.action_name == "create_assignment"
    assert applied.result_resource_type == "assignment"
    assert applied.result_resource_id == assignment.id
    assert applied.error_message is None


def test_rejected_operation_does_not_execute(db_session) -> None:
    parser = RuleBasedOperationParser(tz=DEFAULT_TZ)
    parsed = parser.parse("添加作业 高数作业 2026-06-10 20:00", source="feishu")
    pending = create_pending_operation(db_session, parsed)

    executor = ActionExecutor(db_session)
    rejected = executor.reject(pending.id)

    assert rejected.status == PendingOperationStatus.REJECTED.value
    assert db_session.query(Assignment).count() == 0
    assert db_session.query(PendingOperation).count() == 1
