from __future__ import annotations

from datetime import datetime, timedelta

from app.actions.executor import ActionExecutor
from app.db.models import PendingOperation, PendingOperationStatus, Reminder
from app.secretary.rules import DEFAULT_TZ


def _action(event_type: str, title: str, start_at: datetime, **extra):
    return {
        "action": "create_event",
        "source": "feishu",
        "raw_text": title,
        "actor": {"platform": "feishu", "user_id": "ou_test", "chat_id": "oc_test"},
        "request": {
            "timezone": "Asia/Shanghai",
            "now": "2026-06-07T18:00:00+08:00",
        },
        "payload": {
            "event": {
                "event_type": event_type,
                "title": title,
                "start_at": start_at.isoformat(),
                **extra,
            }
        },
    }


def test_action_executor_create_plan_defaults_one_hour_result(db_session):
    start = datetime(2026, 6, 7, 21, 0, tzinfo=DEFAULT_TZ)

    result = ActionExecutor(db_session).execute(
        _action("plan", "复习劳动法律法规", start)
    )

    assert result["ok"] is True
    assert result["action"] == "create_event"
    assert result["status"] == "pending_confirmation"
    assert result["operation_id"] is not None
    preview = result["data"]["preview"]
    assert preview["event_type"] == "plan"
    assert preview["title"] == "复习劳动法律法规"
    assert preview["start_at"] == start.isoformat()
    assert preview["end_at"] == (start + timedelta(hours=1)).isoformat()
    assert result["debug"]["model_input"]["action"] == "create_event"
    assert result["debug"]["db_result"]["status"] == "pending_confirmation"

    pending = db_session.get(PendingOperation, result["operation_id"])
    assert pending is not None
    assert pending.status == PendingOperationStatus.PENDING.value


def test_action_executor_confirm_schedule_creates_two_default_reminders(db_session):
    start = datetime(2026, 6, 7, 22, 0, tzinfo=DEFAULT_TZ)
    executor = ActionExecutor(db_session)
    result = executor.execute(_action("schedule", "提醒我写作业", start))

    applied = executor.confirm_and_apply_result(result["operation_id"])

    assert applied["ok"] is True
    assert applied["status"] == "applied"
    event = applied["data"]["event"]
    assert event["event_type"] == "schedule"
    assert event["start_at"] == start.isoformat()
    assert event["reminders"] == [
        (start - timedelta(minutes=30)).isoformat(),
        (start - timedelta(minutes=15)).isoformat(),
    ]
    reminders = db_session.query(Reminder).order_by(Reminder.scheduled_at.asc()).all()
    assert [item.scheduled_at for item in reminders] == [
        start - timedelta(minutes=30),
        start - timedelta(minutes=15),
    ]


def test_action_executor_rejects_schedule_without_start_at(db_session):
    result = ActionExecutor(db_session).execute(
        {
            "action": "create_event",
            "source": "feishu",
            "raw_text": "提醒我写作业",
            "payload": {
                "event": {
                    "event_type": "schedule",
                    "title": "提醒我写作业",
                }
            },
        }
    )

    assert result["ok"] is False
    assert result["status"] == "failed"
    assert result["message_code"] == "MISSING_START_AT"
    assert db_session.query(PendingOperation).count() == 0


def test_action_executor_query_result_uses_candidate_refs_not_database_ids(db_session):
    start = datetime(2026, 6, 7, 21, 0, tzinfo=DEFAULT_TZ)
    executor = ActionExecutor(db_session)
    pending = executor.execute(_action("plan", "复习劳动法律法规", start))
    executor.confirm_and_apply_result(pending["operation_id"])

    result = executor.execute(
        {
            "action": "query_event",
            "source": "feishu",
            "raw_text": "今晚有什么事",
            "payload": {
                "filter": {
                    "event_type": "all",
                    "time_range": {
                        "start": "2026-06-07T18:00:00+08:00",
                        "end": "2026-06-08T00:00:00+08:00",
                    },
                    "limit": 10,
                }
            },
        }
    )

    assert result["ok"] is True
    assert result["status"] == "applied"
    events = result["data"]["events"]
    assert events == [
        {
            "ref": "c1",
            "event_type": "plan",
            "title": "复习劳动法律法规",
            "status": "pending",
            "start_at": start.isoformat(),
            "end_at": (start + timedelta(hours=1)).isoformat(),
            "time_label": "2026-06-07 21:00-22:00",
        }
    ]
    assert "id" not in events[0]
    assert result["debug"]["db_result"]["count"] == 1
