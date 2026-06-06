from __future__ import annotations

from datetime import datetime, timedelta

from app.actions.executor import ActionExecutor
from app.db import crud
from app.db.models import (
    Assignment,
    AssignmentStatus,
    CourseSession,
    LifeEvent,
    LifeEventStatus,
    PendingOperation,
    PendingOperationStatus,
    Reminder,
    ReminderStatus,
)
from app.operations.parser import ParsedOperation, RuleBasedOperationParser
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


def test_rule_parser_creates_life_event_operation() -> None:
    parser = RuleBasedOperationParser(tz=DEFAULT_TZ)

    operation = parser.parse("添加事项 洗衣服", source="feishu")

    assert operation.action_name == "create_life_event"
    assert operation.needs_confirmation is True
    assert operation.payload == {
        "resource": "life_event",
        "fields": {"title": "洗衣服"},
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


def test_pending_life_event_confirm_executes_action(db_session) -> None:
    parser = RuleBasedOperationParser(tz=DEFAULT_TZ)
    parsed = parser.parse("添加事项 洗衣服", source="feishu")
    pending = create_pending_operation(db_session, parsed)

    executor = ActionExecutor(db_session)
    applied = executor.confirm_and_apply(pending.id)

    event = db_session.query(LifeEvent).filter_by(title="洗衣服").one()
    assert applied.status == PendingOperationStatus.APPLIED.value
    assert applied.action_name == "create_life_event"
    assert applied.result_resource_type == "life_event"
    assert applied.result_resource_id == event.id
    assert applied.error_message is None


def test_pending_life_event_confirm_preserves_scheduled_at(db_session) -> None:
    parser = RuleBasedOperationParser(tz=DEFAULT_TZ)
    parsed = parser.parse("添加事项 做程设作业", source="feishu")
    parsed.payload["fields"]["scheduled_at"] = "2026-06-05T20:00:00+08:00"
    pending = create_pending_operation(db_session, parsed)

    executor = ActionExecutor(db_session)
    executor.confirm_and_apply(pending.id)

    event = db_session.query(LifeEvent).filter_by(title="做程设作业").one()
    scheduled_at = event.scheduled_at
    if scheduled_at is not None and scheduled_at.tzinfo is None:
        scheduled_at = scheduled_at.replace(tzinfo=DEFAULT_TZ)
    assert scheduled_at == datetime(2026, 6, 5, 20, 0, tzinfo=DEFAULT_TZ)


def test_pending_life_event_confirm_creates_default_pre_event_reminder(
    db_session,
) -> None:
    parser = RuleBasedOperationParser(tz=DEFAULT_TZ)
    parsed = parser.parse("添加事项 做程设作业", source="feishu")
    parsed.payload["fields"]["scheduled_at"] = "2026-06-05T20:00:00+08:00"
    pending = create_pending_operation(db_session, parsed)

    executor = ActionExecutor(db_session)
    executor.confirm_and_apply(pending.id)

    event = db_session.query(LifeEvent).filter_by(title="做程设作业").one()
    reminder = db_session.query(Reminder).filter_by(target_type="life_event").one()
    reminder_at = reminder.scheduled_at
    if reminder_at is not None and reminder_at.tzinfo is None:
        reminder_at = reminder_at.replace(tzinfo=DEFAULT_TZ)
    assert reminder.target_id == event.id
    assert reminder.reminder_type == "life_event_pre_event"
    assert reminder_at == datetime(2026, 6, 5, 19, 45, tzinfo=DEFAULT_TZ)
    assert "做程设作业" in (reminder.content or "")


def test_pending_life_event_confirm_respects_custom_reminder_lead_minutes(
    db_session,
) -> None:
    parser = RuleBasedOperationParser(tz=DEFAULT_TZ)
    parsed = parser.parse("添加事项 做程设作业", source="feishu")
    scheduled_at = datetime(2026, 6, 5, 20, 0, tzinfo=DEFAULT_TZ)
    parsed.payload["fields"]["scheduled_at"] = scheduled_at.isoformat()
    parsed.payload["fields"]["reminder_lead_minutes"] = 30
    pending = create_pending_operation(db_session, parsed)

    executor = ActionExecutor(db_session)
    executor.confirm_and_apply(pending.id)

    reminder = db_session.query(Reminder).filter_by(target_type="life_event").one()
    reminder_at = reminder.scheduled_at
    if reminder_at is not None and reminder_at.tzinfo is None:
        reminder_at = reminder_at.replace(tzinfo=DEFAULT_TZ)
    assert reminder_at == scheduled_at - timedelta(minutes=30)


def test_event_interface_create_supports_three_event_types(db_session) -> None:
    operations = [
        ParsedOperation(
            source="feishu",
            raw_text="新增作业",
            action_name="create_event",
            payload={
                "operation": "create",
                "resource": "event",
                "selector": {},
                "fields": {
                    "event_type": "assignment",
                    "title": "线代作业",
                    "due_at": "2026-06-10T20:00:00+08:00",
                },
            },
            confidence=0.9,
            needs_confirmation=True,
        ),
        ParsedOperation(
            source="feishu",
            raw_text="新增生活事项",
            action_name="create_event",
            payload={
                "operation": "create",
                "resource": "event",
                "selector": {},
                "fields": {
                    "event_type": "life_event",
                    "title": "吃饭",
                    "scheduled_at": "2026-06-05T22:00:00+08:00",
                    "reminder_lead_minutes": 15,
                },
            },
            confidence=0.9,
            needs_confirmation=True,
        ),
        ParsedOperation(
            source="feishu",
            raw_text="新增课程",
            action_name="create_event",
            payload={
                "operation": "create",
                "resource": "event",
                "selector": {},
                "fields": {
                    "event_type": "course_session",
                    "course_name": "物理",
                    "teacher": "Dr. Lee",
                    "weekday": 2,
                    "start_time": "10:00",
                    "end_time": "11:40",
                    "location": "B201",
                },
            },
            confidence=0.9,
            needs_confirmation=True,
        ),
    ]

    for operation in operations:
        pending = create_pending_operation(db_session, operation)
        applied = ActionExecutor(db_session).confirm_and_apply(pending.id)
        assert applied.status == PendingOperationStatus.APPLIED.value

    assert db_session.query(Assignment).filter_by(title="线代作业").one()
    event = db_session.query(LifeEvent).filter_by(title="吃饭").one()
    reminder = db_session.query(Reminder).filter_by(target_type="life_event").one()
    session = db_session.query(CourseSession).one()
    assert reminder.target_id == event.id
    assert session.course.name == "物理"
    assert session.location_override == "B201"


def test_event_interface_update_and_delete_events(db_session) -> None:
    assignment = crud.create_assignment(db_session, title="旧作业")
    life_event = crud.create_life_event(db_session, title="旧事项")

    update = ParsedOperation(
        source="feishu",
        raw_text="修改事项",
        action_name="update_event",
        payload={
            "operation": "update",
            "resource": "event",
            "selector": {"event_type": "life_event", "id": life_event.id},
            "fields": {
                "title": "新事项",
                "scheduled_at": "2026-06-05T21:00:00+08:00",
                "notes": "updated",
            },
        },
        confidence=0.9,
        needs_confirmation=True,
    )
    delete = ParsedOperation(
        source="feishu",
        raw_text="删除作业",
        action_name="delete_event",
        payload={
            "operation": "delete",
            "resource": "event",
            "selector": {"event_type": "assignment", "id": assignment.id},
            "fields": {},
        },
        confidence=0.9,
        needs_confirmation=True,
    )

    ActionExecutor(db_session).confirm_and_apply(create_pending_operation(db_session, update).id)
    ActionExecutor(db_session).confirm_and_apply(create_pending_operation(db_session, delete).id)

    db_session.refresh(assignment)
    db_session.refresh(life_event)
    assert assignment.status == AssignmentStatus.CANCELLED.value
    assert life_event.title == "新事项"
    assert life_event.notes == "updated"
    scheduled_at = life_event.scheduled_at
    if scheduled_at is not None and scheduled_at.tzinfo is None:
        scheduled_at = scheduled_at.replace(tzinfo=DEFAULT_TZ)
    assert scheduled_at == datetime(2026, 6, 5, 21, 0, tzinfo=DEFAULT_TZ)


def test_event_interface_update_and_delete_course_session(db_session) -> None:
    course = crud.create_course(db_session, name="物理")
    session = crud.create_course_session(
        db_session,
        course_id=course.id,
        weekday=2,
        start_time="10:00",
        end_time="11:40",
        location_override="B201",
    )

    update = ParsedOperation(
        source="feishu",
        raw_text="修改课程",
        action_name="update_event",
        payload={
            "operation": "update",
            "resource": "event",
            "selector": {"event_type": "course_session", "id": session.id},
            "fields": {
                "weekday": 3,
                "start_time": "14:00",
                "end_time": "15:40",
                "location": "C301",
            },
        },
        confidence=0.9,
        needs_confirmation=True,
    )

    applied = ActionExecutor(db_session).confirm_and_apply(
        create_pending_operation(db_session, update).id
    )

    db_session.refresh(session)
    assert applied.status == PendingOperationStatus.APPLIED.value
    assert session.weekday == 3
    assert session.start_time == "14:00"
    assert session.end_time == "15:40"
    assert session.location_override == "C301"

    delete = ParsedOperation(
        source="feishu",
        raw_text="删除课程",
        action_name="delete_event",
        payload={
            "operation": "delete",
            "resource": "event",
            "selector": {"event_type": "course_session", "id": session.id},
            "fields": {},
        },
        confidence=0.9,
        needs_confirmation=True,
    )

    deleted = ActionExecutor(db_session).confirm_and_apply(
        create_pending_operation(db_session, delete).id
    )

    assert deleted.status == PendingOperationStatus.APPLIED.value
    assert db_session.get(CourseSession, session.id) is None


def test_event_interface_query_events(db_session) -> None:
    crud.create_assignment(db_session, title="待交作业")
    done_assignment = crud.create_assignment(db_session, title="已完成作业")
    done_assignment.status = AssignmentStatus.DONE.value
    crud.create_life_event(db_session, title="待做事项")
    cancelled_event = crud.create_life_event(db_session, title="已取消事项")
    cancelled_event.status = LifeEventStatus.CANCELLED.value
    db_session.commit()

    results = ActionExecutor(db_session).query_events(
        {
            "operation": "query",
            "resource": "event",
            "selector": {},
            "fields": {"event_type": "all", "status": "open"},
        }
    )

    titles = {item["title"] for item in results}
    assert titles == {"待交作业", "待做事项"}
    assert {item["event_type"] for item in results} == {"assignment", "life_event"}


def test_pending_update_reminder_confirm_executes_action(db_session) -> None:
    reminder = crud.create_reminder(
        db_session,
        reminder_type="life_event_pre_event",
        target_type="life_event",
        scheduled_at=datetime(2026, 6, 5, 19, 45, tzinfo=DEFAULT_TZ),
        content="提醒：洗澡",
    )
    parsed = ParsedOperation(
        source="feishu",
        raw_text="把提醒改到 20:30",
        action_name="update_reminder",
        payload={
            "operation": "update",
            "resource": "reminder",
            "selector": {"id": reminder.id},
            "fields": {"scheduled_at": "2026-06-05T20:30:00+08:00"},
        },
        confidence=0.86,
        needs_confirmation=True,
    )
    pending = create_pending_operation(db_session, parsed)

    applied = ActionExecutor(db_session).confirm_and_apply(pending.id)

    db_session.refresh(reminder)
    scheduled_at = reminder.scheduled_at
    if scheduled_at is not None and scheduled_at.tzinfo is None:
        scheduled_at = scheduled_at.replace(tzinfo=DEFAULT_TZ)
    assert scheduled_at == datetime(2026, 6, 5, 20, 30, tzinfo=DEFAULT_TZ)
    assert applied.status == PendingOperationStatus.APPLIED.value
    assert applied.result_resource_type == "reminder"
    assert applied.result_resource_id == reminder.id


def test_pending_cancel_reminder_confirm_executes_action(db_session) -> None:
    reminder = crud.create_reminder(
        db_session,
        reminder_type="life_event_pre_event",
        target_type="life_event",
        scheduled_at=datetime(2026, 6, 5, 19, 45, tzinfo=DEFAULT_TZ),
        content="提醒：洗澡",
    )
    parsed = ParsedOperation(
        source="feishu",
        raw_text="取消提醒",
        action_name="cancel_reminder",
        payload={
            "operation": "cancel",
            "resource": "reminder",
            "selector": {"id": reminder.id},
            "fields": {},
        },
        confidence=0.86,
        needs_confirmation=True,
    )
    pending = create_pending_operation(db_session, parsed)

    applied = ActionExecutor(db_session).confirm_and_apply(pending.id)

    db_session.refresh(reminder)
    assert reminder.status == ReminderStatus.CANCELLED.value
    assert applied.status == PendingOperationStatus.APPLIED.value
    assert applied.result_resource_type == "reminder"
    assert applied.result_resource_id == reminder.id


def test_life_event_create_rolls_back_when_reminder_creation_fails(
    db_session,
    monkeypatch,
) -> None:
    parser = RuleBasedOperationParser(tz=DEFAULT_TZ)
    parsed = parser.parse("添加事项 洗澡", source="feishu")
    parsed.payload["fields"]["scheduled_at"] = "2026-06-05T20:00:00+08:00"
    pending = create_pending_operation(db_session, parsed)

    def fail_create_reminder(*args, **kwargs):
        raise RuntimeError("reminder write failed")

    monkeypatch.setattr(crud, "create_reminder", fail_create_reminder)

    applied = ActionExecutor(db_session).confirm_and_apply(pending.id)

    assert applied.status == PendingOperationStatus.FAILED.value
    assert "reminder write failed" in (applied.error_message or "")
    assert db_session.query(LifeEvent).filter_by(title="洗澡").count() == 0
    assert db_session.query(Reminder).count() == 0


def test_failed_cancel_reminder_records_audit_without_mutating_sent_reminder(
    db_session,
) -> None:
    reminder = crud.create_reminder(
        db_session,
        reminder_type="life_event_pre_event",
        target_type="life_event",
        scheduled_at=datetime(2026, 6, 5, 19, 45, tzinfo=DEFAULT_TZ),
        status=ReminderStatus.SENT,
        content="提醒：洗澡",
    )
    parsed = ParsedOperation(
        source="feishu",
        raw_text="取消已发送提醒",
        action_name="cancel_reminder",
        payload={
            "operation": "cancel",
            "resource": "reminder",
            "selector": {"id": reminder.id},
            "fields": {},
        },
        confidence=0.86,
        needs_confirmation=True,
    )
    pending = create_pending_operation(db_session, parsed)

    applied = ActionExecutor(db_session).confirm_and_apply(pending.id)

    db_session.refresh(reminder)
    assert reminder.status == ReminderStatus.SENT.value
    assert applied.status == PendingOperationStatus.FAILED.value
    assert "already sent" in (applied.error_message or "")
    assert applied.result_resource_type == "reminder"
    assert applied.result_resource_id == reminder.id
