from __future__ import annotations

from datetime import datetime

from app.actions.executor import ActionExecutor
from app.actions.protocol import default_reminder_times
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
)
from app.operations.parser import ParsedOperation
from app.operations.store import create_pending_operation
from app.scheduler.reminder_engine import ReminderEngine, SchedulerConfig
from app.secretary.rules import DEFAULT_TZ
from tests.conftest import make_create_event, make_delete_event, make_update_event


class RecordingSender:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def send(self, *, card=None, text: str = "") -> None:
        self.messages.append(text)


def test_action_protocol_create_deadline_operation() -> None:
    operation = make_create_event(
        event_type="deadline",
        title="高数作业",
        start_at="2026-06-10T20:00:00+08:00",
        raw_text="添加作业 高数作业 2026-06-10 20:00",
    )

    assert operation.source == "feishu"
    assert operation.action_name == "create_event"
    assert operation.needs_confirmation is True
    assert operation.payload["action"] == "create_event"
    assert operation.payload["payload"]["event"]["event_type"] == "deadline"
    assert operation.payload["payload"]["event"]["title"] == "高数作业"


def test_action_protocol_create_schedule_operation() -> None:
    operation = make_create_event(
        event_type="schedule",
        title="洗衣服",
        raw_text="添加事项 洗衣服",
    )

    assert operation.action_name == "create_event"
    assert operation.payload["payload"]["event"]["event_type"] == "schedule"


def test_pending_operation_confirm_executes_action(db_session) -> None:
    parsed = make_create_event(
        event_type="deadline",
        title="高数作业",
        start_at="2026-06-10T20:00:00+08:00",
        raw_text="添加作业 高数作业 2026-06-10 20:00",
    )
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
    assert applied.action_name == "create_event"
    assert applied.result_resource_type == "assignment"
    assert applied.result_resource_id == assignment.id
    assert applied.error_message is None


def test_rejected_operation_does_not_execute(db_session) -> None:
    parsed = make_create_event(
        event_type="deadline",
        title="高数作业",
        start_at="2026-06-10T20:00:00+08:00",
    )
    pending = create_pending_operation(db_session, parsed)

    executor = ActionExecutor(db_session)
    rejected = executor.reject(pending.id)

    assert rejected.status == PendingOperationStatus.REJECTED.value
    assert db_session.query(Assignment).count() == 0
    assert db_session.query(PendingOperation).count() == 1


def test_pending_life_event_confirm_executes_action(db_session) -> None:
    parsed = make_create_event(
        event_type="schedule",
        title="洗衣服",
        raw_text="添加事项 洗衣服",
    )
    pending = create_pending_operation(db_session, parsed)

    executor = ActionExecutor(db_session)
    applied = executor.confirm_and_apply(pending.id)

    event = db_session.query(LifeEvent).filter_by(title="洗衣服").one()
    assert applied.status == PendingOperationStatus.APPLIED.value
    assert applied.action_name == "create_event"
    assert applied.result_resource_type == "life_event"
    assert applied.result_resource_id == event.id
    assert applied.error_message is None


def test_pending_life_event_confirm_preserves_scheduled_at(db_session) -> None:
    parsed = make_create_event(
        event_type="schedule",
        title="做程设作业",
        start_at="2026-06-05T20:00:00+08:00",
        raw_text="添加事项 做程设作业",
    )
    pending = create_pending_operation(db_session, parsed)

    executor = ActionExecutor(db_session)
    executor.confirm_and_apply(pending.id)

    event = db_session.query(LifeEvent).filter_by(title="做程设作业").one()
    scheduled_at = event.scheduled_at
    if scheduled_at is not None and scheduled_at.tzinfo is None:
        scheduled_at = scheduled_at.replace(tzinfo=DEFAULT_TZ)
    assert scheduled_at == datetime(2026, 6, 5, 20, 0, tzinfo=DEFAULT_TZ)


def test_pending_schedule_confirm_uses_default_reminder_scan_times(db_session) -> None:
    start_at = datetime(2026, 6, 5, 20, 0, tzinfo=DEFAULT_TZ)
    parsed = make_create_event(
        event_type="schedule",
        title="做程设作业",
        start_at=start_at.isoformat(),
        raw_text="添加事项 做程设作业",
    )
    pending = create_pending_operation(db_session, parsed)

    ActionExecutor(db_session).confirm_and_apply(pending.id)

    event = db_session.query(LifeEvent).filter_by(title="做程设作业").one()
    engine = ReminderEngine(SchedulerConfig(tz=DEFAULT_TZ))
    first_reminder = default_reminder_times(start_at)[0]
    due = engine.collect_due_notifications(
        db_session,
        now=first_reminder,
    )
    assert any(item.target_id == event.id for item in due)
    assert db_session.query(Reminder).count() == 0


def test_event_interface_create_supports_public_event_types(db_session) -> None:
    operations = [
        make_create_event(
            event_type="deadline",
            title="线代作业",
            start_at="2026-06-10T20:00:00+08:00",
            raw_text="新增作业",
        ),
        make_create_event(
            event_type="schedule",
            title="吃饭",
            start_at="2026-06-05T22:00:00+08:00",
            raw_text="新增生活事项",
        ),
        make_create_event(
            event_type="plan",
            title="物理复习",
            start_at="2026-06-05T10:00:00+08:00",
            end_at="2026-06-05T11:40:00+08:00",
            raw_text="新增计划",
        ),
    ]

    for operation in operations:
        pending = create_pending_operation(db_session, operation)
        applied = ActionExecutor(db_session).confirm_and_apply(pending.id)
        assert applied.status == PendingOperationStatus.APPLIED.value

    assert db_session.query(Assignment).filter_by(title="线代作业").one()
    assert db_session.query(LifeEvent).filter_by(title="吃饭").one()
    assert db_session.query(LifeEvent).filter_by(title="物理复习").one()


def test_event_interface_update_and_delete_events(db_session) -> None:
    assignment = crud.create_assignment(db_session, title="旧作业")
    life_event = crud.create_life_event(db_session, title="旧事项")

    update = make_update_event(
        event_type="schedule",
        resource_id=life_event.id,
        patch={
            "title": "新事项",
            "start_at": "2026-06-05T21:00:00+08:00",
            "notes": "updated",
        },
        raw_text="修改事项",
    )
    delete = make_delete_event(
        event_type="deadline",
        resource_id=assignment.id,
        raw_text="删除作业",
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


def test_update_life_event_changes_scheduled_at(db_session) -> None:
    event = crud.create_life_event(
        db_session,
        title="做程序设计作业",
        scheduled_at=datetime(2026, 6, 6, 20, 0, tzinfo=DEFAULT_TZ),
    )
    parsed = make_update_event(
        event_type="schedule",
        resource_id=event.id,
        patch={"start_at": "2026-06-06T22:00:00+08:00"},
        raw_text="把程设作业改到十点",
    )

    applied = ActionExecutor(db_session).confirm_and_apply(
        create_pending_operation(db_session, parsed).id
    )

    db_session.refresh(event)
    event_time = event.scheduled_at
    if event_time is not None and event_time.tzinfo is None:
        event_time = event_time.replace(tzinfo=DEFAULT_TZ)
    assert applied.status == PendingOperationStatus.APPLIED.value
    assert event_time == datetime(2026, 6, 6, 22, 0, tzinfo=DEFAULT_TZ)


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

    update = make_update_event(
        event_type="course",
        resource_id=session.id,
        patch={
            "weekday": 3,
            "start_time": "14:00",
            "end_time": "15:40",
            "location": "C301",
        },
        raw_text="修改课程",
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

    delete = make_delete_event(
        event_type="course",
        resource_id=session.id,
        raw_text="删除课程",
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
            "filter": {"event_type": "all", "status": ["pending", "active"]},
        }
    )

    titles = {item["title"] for item in results}
    assert titles == {"待交作业", "待做事项"}
    assert {item["event_type"] for item in results} == {"deadline", "schedule"}


def test_event_query_filters_by_time_range_and_returns_compact_candidates(
    db_session,
) -> None:
    crud.create_life_event(
        db_session,
        title="做程序设计作业",
        scheduled_at=datetime(2026, 6, 6, 20, 0, tzinfo=DEFAULT_TZ),
        notes="这是一段很长的备注，不应该进入二阶段候选短列表",
    )
    crud.create_life_event(
        db_session,
        title="明天跑步",
        scheduled_at=datetime(2026, 6, 7, 20, 0, tzinfo=DEFAULT_TZ),
    )
    crud.create_assignment(
        db_session,
        title="今晚交线代",
        due_at=datetime(2026, 6, 6, 23, 0, tzinfo=DEFAULT_TZ),
    )

    results = ActionExecutor(db_session).query_events(
        {
            "filter": {
                "event_type": "all",
                "status": ["pending", "active"],
                "time_range": {
                    "start": "2026-06-06T18:00:00+08:00",
                    "end": "2026-06-07T00:00:00+08:00",
                },
                "limit": 10,
            },
        }
    )

    assert {item["title"] for item in results} == {"做程序设计作业", "今晚交线代"}
    for item in results:
        assert set(item) <= {
            "end_at",
            "event_type",
            "ref",
            "start_at",
            "status",
            "time_label",
            "title",
        }
        assert item["time_label"]


def test_legacy_update_reminder_action_is_rejected(db_session) -> None:
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
            "action": "update_reminder",
            "source": "feishu",
            "raw_text": "把提醒改到 20:30",
            "payload": {
                "selector": {"id": reminder.id},
                "patch": {"scheduled_at": "2026-06-05T20:30:00+08:00"},
            },
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
    assert scheduled_at == datetime(2026, 6, 5, 19, 45, tzinfo=DEFAULT_TZ)
    assert applied.status == PendingOperationStatus.FAILED.value
    assert "unsupported action" in (applied.error_message or "")
    assert applied.result_resource_type is None
    assert applied.result_resource_id is None


def test_legacy_cancel_reminder_action_is_rejected(db_session) -> None:
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
            "action": "cancel_reminder",
            "source": "feishu",
            "raw_text": "取消提醒",
            "payload": {"selector": {"id": reminder.id}},
        },
        confidence=0.86,
        needs_confirmation=True,
    )
    pending = create_pending_operation(db_session, parsed)

    applied = ActionExecutor(db_session).confirm_and_apply(pending.id)

    db_session.refresh(reminder)
    assert reminder.status == "pending"
    assert applied.status == PendingOperationStatus.FAILED.value
    assert "unsupported action" in (applied.error_message or "")
    assert applied.result_resource_type is None
    assert applied.result_resource_id is None


def test_delete_event_can_apply_resolved_batch_targets(db_session) -> None:
    first = crud.create_life_event(
        db_session,
        title="今晚事项 A",
        scheduled_at=datetime(2026, 6, 6, 20, 0, tzinfo=DEFAULT_TZ),
    )
    second = crud.create_life_event(
        db_session,
        title="今晚事项 B",
        scheduled_at=datetime(2026, 6, 6, 21, 0, tzinfo=DEFAULT_TZ),
    )
    tomorrow = crud.create_life_event(
        db_session,
        title="明晚事项",
        scheduled_at=datetime(2026, 6, 7, 20, 0, tzinfo=DEFAULT_TZ),
    )
    parsed = make_delete_event(
        event_type="schedule",
        targets=[
            {"event_type": "schedule", "id": first.id},
            {"event_type": "schedule", "id": second.id},
        ],
        raw_text="删除今晚的所有事项",
    )

    applied = ActionExecutor(db_session).confirm_and_apply(
        create_pending_operation(db_session, parsed).id
    )

    db_session.refresh(first)
    db_session.refresh(second)
    db_session.refresh(tomorrow)
    assert applied.status == PendingOperationStatus.APPLIED.value
    assert first.status == LifeEventStatus.CANCELLED.value
    assert second.status == LifeEventStatus.CANCELLED.value
    assert tomorrow.status == LifeEventStatus.PENDING.value


def test_delete_event_batch_failure_does_not_partially_mutate_targets(
    db_session,
) -> None:
    first = crud.create_life_event(
        db_session,
        title="今晚事项 A",
        scheduled_at=datetime(2026, 6, 6, 20, 0, tzinfo=DEFAULT_TZ),
    )
    parsed = make_delete_event(
        event_type="schedule",
        targets=[
            {"event_type": "schedule", "id": first.id},
            {"event_type": "schedule", "id": 9999},
        ],
        raw_text="删除两个事项",
    )

    applied = ActionExecutor(db_session).confirm_and_apply(
        create_pending_operation(db_session, parsed).id
    )

    db_session.refresh(first)
    assert applied.status == PendingOperationStatus.FAILED.value
    assert "not found" in (applied.error_message or "")
    assert first.status == LifeEventStatus.PENDING.value
