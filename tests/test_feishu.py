from __future__ import annotations

import json
import time
from datetime import date, datetime
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import crud
from app.db.models import (
    Assignment,
    LifeEvent,
    MessageLog,
    PendingOperation,
    PendingOperationStatus,
    ReminderStatus,
)
from app.feishu.cards import build_pending_operation_card
from app.feishu.client import FeishuClient
from app.feishu.commands import (
    COMMAND_ADD_ASSIGNMENT,
    COMMAND_CANCEL_REMINDER,
    COMMAND_COMPLETE,
    COMMAND_HELP,
    COMMAND_REMINDERS,
    COMMAND_TODAY,
    COMMAND_TODOS,
    COMMAND_UPDATE_REMINDER,
    COMMAND_WEEKLY_DDL,
    execute_command,
    format_help_message,
    parse_command,
)
from app.feishu.event_handler import FeishuEventHandler
from app.feishu.security import (
    FeishuSecurityError,
    compute_signature,
    parse_event_payload,
    validate_request_headers,
    verify_signature,
    verify_timestamp,
    verify_token,
)
from app.operations.parser import ParsedOperation
from app.secretary.rules import DEFAULT_TZ

TEST_TOKEN = "test-verification-token"
TEST_ENCRYPT_KEY = "test-encrypt-key"
TEST_APP_ID = "cli_test_app"
TEST_APP_SECRET = "test-app-secret"
FIXED_NOW = 1_700_000_000.0


@pytest.fixture
def feishu_settings(monkeypatch, db_session):
    monkeypatch.setenv("FEISHU_VERIFICATION_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("FEISHU_ENCRYPT_KEY", TEST_ENCRYPT_KEY)
    monkeypatch.setenv("FEISHU_APP_ID", TEST_APP_ID)
    monkeypatch.setenv("FEISHU_APP_SECRET", TEST_APP_SECRET)
    monkeypatch.setenv("FEISHU_DEFAULT_CHAT_ID", "oc_default_chat")
    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


@pytest.fixture
def mock_feishu_client():
    client = MagicMock(spec=FeishuClient)
    client.send_text.return_value = {"code": 0}
    client.send_interactive_card.return_value = {"code": 0}
    client.delete_message.return_value = {"code": 0}
    return client


@pytest.fixture
def event_handler(feishu_settings, mock_feishu_client):
    return FeishuEventHandler(feishu_settings, client=mock_feishu_client)


def _signed_headers(
    body: str,
    *,
    now: float = FIXED_NOW,
    nonce: str = "nonce-123",
) -> dict[str, str]:
    timestamp = str(int(now))
    signature = compute_signature(timestamp, nonce, TEST_ENCRYPT_KEY, body)
    return {
        "X-Lark-Request-Timestamp": timestamp,
        "X-Lark-Request-Nonce": nonce,
        "X-Lark-Signature": signature,
    }


def _message_event(
    text: str,
    *,
    token: str = TEST_TOKEN,
    chat_id: str = "oc_chat_1",
    message_id: str = "om_msg_1",
) -> dict[str, Any]:
    return {
        "schema": "2.0",
        "header": {
            "event_type": "im.message.receive_v1",
            "token": token,
        },
        "event": {
            "message": {
                "message_id": message_id,
                "chat_id": chat_id,
                "message_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            }
        },
    }


def _card_action_event(
    action: str,
    operation_id: int,
    *,
    token: str = TEST_TOKEN,
) -> dict[str, Any]:
    return {
        "schema": "2.0",
        "header": {
            "event_type": "card.action.trigger",
            "token": token,
        },
        "event": {
            "action": {
                "value": {
                    "smartcore_action": action,
                    "operation_id": operation_id,
                }
            },
            "context": {
                "open_chat_id": "oc_chat_1",
                "open_message_id": "om_card_1",
            },
        },
    }


def test_verify_token_rejects_invalid():
    assert verify_token("wrong", TEST_TOKEN) is False
    assert verify_token(None, TEST_TOKEN) is False


def test_verify_token_accepts_valid():
    assert verify_token(TEST_TOKEN, TEST_TOKEN) is True


def test_verify_signature_rejects_invalid():
    assert (
        verify_signature("1700000000", "nonce", TEST_ENCRYPT_KEY, "{}", "deadbeef")
        is False
    )


def test_verify_signature_accepts_valid():
    body = '{"hello":"world"}'
    timestamp = "1700000000"
    nonce = "abc"
    signature = compute_signature(timestamp, nonce, TEST_ENCRYPT_KEY, body)
    assert verify_signature(timestamp, nonce, TEST_ENCRYPT_KEY, body, signature) is True


def test_verify_timestamp_rejects_replay():
    old_ts = str(int(FIXED_NOW - 600))
    assert verify_timestamp(old_ts, now=FIXED_NOW, max_age_seconds=300) is False


def test_verify_timestamp_accepts_recent():
    recent_ts = str(int(FIXED_NOW - 30))
    assert verify_timestamp(recent_ts, now=FIXED_NOW, max_age_seconds=300) is True


def test_validate_request_headers_rejects_bad_signature():
    body = "{}"
    headers = _signed_headers(body)
    headers["X-Lark-Signature"] = "invalid"
    with pytest.raises(FeishuSecurityError, match="invalid signature"):
        validate_request_headers(headers, encrypt_key=TEST_ENCRYPT_KEY, body=body, now=FIXED_NOW)


def test_parse_event_payload_rejects_invalid_token():
    body = json.dumps({"type": "url_verification", "token": "bad", "challenge": "x"})
    with pytest.raises(FeishuSecurityError, match="invalid verification token"):
        parse_event_payload(body, encrypt_key=TEST_ENCRYPT_KEY, verification_token=TEST_TOKEN)


def test_parse_command_maps_known_commands():
    assert parse_command("今日").name == COMMAND_TODAY
    assert parse_command("今天有啥事").name == COMMAND_TODAY
    assert parse_command("今天有什么安排").name == COMMAND_TODAY
    assert parse_command("本周DDL").name == COMMAND_WEEKLY_DDL
    assert parse_command("待办").name == COMMAND_TODOS
    assert parse_command("待完成事项").name == COMMAND_TODOS
    assert parse_command("还有什么没做").name == COMMAND_TODOS
    assert parse_command("提醒队列").name == COMMAND_REMINDERS
    assert parse_command("取消提醒 12").name == COMMAND_CANCEL_REMINDER
    assert parse_command("修改提醒 12 2026-03-02 20:30").name == COMMAND_UPDATE_REMINDER
    assert parse_command("添加作业 数学作业 2026-03-05").name == COMMAND_ADD_ASSIGNMENT
    assert parse_command("添加事项 洗衣服").name == "add_life_event"
    assert parse_command("完成 数学作业").name == COMMAND_COMPLETE
    assert parse_command("确认 12").name == "confirm_operation"
    assert parse_command("拒绝 12").name == "reject_operation"
    assert parse_command("帮助").name == COMMAND_HELP


def test_parse_command_unknown_returns_help():
    assert parse_command("随便说点什么").name == COMMAND_HELP


def test_help_message_includes_query_commands():
    help_text = format_help_message()

    assert "今天有啥事" in help_text
    assert "待办" in help_text
    assert "待完成事项" in help_text


def test_execute_command_today(db_session):
    crud.create_assignment(
        db_session,
        title="Essay",
        due_at=datetime(2026, 3, 2, 23, 59, tzinfo=DEFAULT_TZ),
    )
    reply = execute_command(
        db_session,
        parse_command("今日"),
        today=date(2026, 3, 2),
    )
    assert "今日晨报" in reply
    assert "Essay" in reply


def test_execute_command_today_includes_pending_reminder_summary(db_session):
    crud.create_reminder(
        db_session,
        reminder_type="life_event_pre_event",
        target_type="life_event",
        scheduled_at=datetime(2026, 3, 2, 19, 45, tzinfo=DEFAULT_TZ),
        content="提醒：洗澡",
    )

    reply = execute_command(
        db_session,
        parse_command("今日"),
        today=date(2026, 3, 2),
    )

    assert "待发送提醒" in reply
    assert "19:45" in reply
    assert "洗澡" in reply


def test_execute_command_reminder_queue_lists_status_groups(db_session):
    crud.create_reminder(
        db_session,
        reminder_type="life_event_pre_event",
        target_type="life_event",
        scheduled_at=datetime(2026, 3, 2, 19, 45, tzinfo=DEFAULT_TZ),
        content="提醒：洗澡",
    )
    crud.create_reminder(
        db_session,
        reminder_type="life_event_pre_event",
        target_type="life_event",
        scheduled_at=datetime(2026, 3, 2, 20, 45, tzinfo=DEFAULT_TZ),
        status=ReminderStatus.SENT,
        content="提醒：跑步",
    )

    reply = execute_command(
        db_session,
        parse_command("提醒队列"),
        today=date(2026, 3, 2),
    )

    assert "【提醒队列】" in reply
    assert "待发送" in reply
    assert "已发送" in reply
    assert "19:45" in reply
    assert "洗澡" in reply
    assert "跑步" in reply


def test_execute_command_cancel_pending_reminder_by_id(db_session):
    reminder = crud.create_reminder(
        db_session,
        reminder_type="life_event_pre_event",
        target_type="life_event",
        scheduled_at=datetime(2026, 3, 2, 19, 45, tzinfo=DEFAULT_TZ),
        content="提醒：洗澡",
    )

    reply = execute_command(
        db_session,
        parse_command(f"取消提醒 {reminder.id}"),
        today=date(2026, 3, 2),
    )

    db_session.refresh(reminder)
    assert reminder.status == ReminderStatus.CANCELLED.value
    assert f"已取消提醒 #{reminder.id}" in reply


def test_execute_command_update_pending_reminder_time_by_id(db_session):
    reminder = crud.create_reminder(
        db_session,
        reminder_type="life_event_pre_event",
        target_type="life_event",
        scheduled_at=datetime(2026, 3, 2, 19, 45, tzinfo=DEFAULT_TZ),
        content="提醒：洗澡",
    )

    reply = execute_command(
        db_session,
        parse_command(f"修改提醒 {reminder.id} 2026-03-02 20:30"),
        today=date(2026, 3, 2),
    )

    db_session.refresh(reminder)
    scheduled_at = reminder.scheduled_at
    if scheduled_at is not None and scheduled_at.tzinfo is None:
        scheduled_at = scheduled_at.replace(tzinfo=DEFAULT_TZ)
    assert scheduled_at == datetime(2026, 3, 2, 20, 30, tzinfo=DEFAULT_TZ)
    assert f"已修改提醒 #{reminder.id}" in reply
    assert "20:30" in reply


def test_execute_command_does_not_cancel_sent_reminder(db_session):
    reminder = crud.create_reminder(
        db_session,
        reminder_type="life_event_pre_event",
        target_type="life_event",
        scheduled_at=datetime(2026, 3, 2, 19, 45, tzinfo=DEFAULT_TZ),
        status=ReminderStatus.SENT,
        content="提醒：洗澡",
    )

    reply = execute_command(
        db_session,
        parse_command(f"取消提醒 {reminder.id}"),
        today=date(2026, 3, 2),
    )

    db_session.refresh(reminder)
    assert reminder.status == ReminderStatus.SENT.value
    assert "无法取消" in reply


def test_execute_command_weekly_ddl(db_session):
    crud.create_assignment(
        db_session,
        title="Lab report",
        due_at=datetime(2026, 3, 4, 18, 0, tzinfo=DEFAULT_TZ),
    )
    reply = execute_command(
        db_session,
        parse_command("本周DDL"),
        today=date(2026, 3, 2),
    )
    assert "Lab report" in reply


def test_execute_command_todos_lists_open_assignments_and_life_events(db_session):
    crud.create_assignment(
        db_session,
        title="Open Essay",
        due_at=datetime(2026, 3, 4, 18, 0, tzinfo=DEFAULT_TZ),
    )
    done_assignment = crud.create_assignment(
        db_session,
        title="Done Essay",
        due_at=datetime(2026, 3, 3, 18, 0, tzinfo=DEFAULT_TZ),
    )
    done_assignment.status = "done"
    crud.create_life_event(
        db_session,
        title="Buy batteries",
        scheduled_at=datetime(2026, 3, 2, 20, 0, tzinfo=DEFAULT_TZ),
    )
    done_event = crud.create_life_event(db_session, title="Already washed clothes")
    done_event.status = "done"
    db_session.commit()

    reply = execute_command(
        db_session,
        parse_command("待办"),
        today=date(2026, 3, 2),
    )

    assert "【待办事项】" in reply
    assert "作业" in reply
    assert "Open Essay" in reply
    assert "生活事项" in reply
    assert "Buy batteries" in reply
    assert "Done Essay" not in reply
    assert "Already washed clothes" not in reply


def test_execute_command_todos_empty_state(db_session):
    reply = execute_command(
        db_session,
        parse_command("还有什么没做"),
        today=date(2026, 3, 2),
    )

    assert "【待办事项】" in reply
    assert "暂无待完成事项" in reply


def test_execute_command_add_and_complete(db_session):
    reply = execute_command(db_session, parse_command("添加作业 数学作业"))
    assert "已添加作业" in reply
    done = execute_command(db_session, parse_command("完成 数学作业"))
    assert "已完成作业" in done


def test_event_handler_rejects_invalid_token(event_handler, db_session):
    body = json.dumps(_message_event("今日", token="bad-token"))
    status, payload = event_handler.handle(
        body.encode(),
        _signed_headers(body),
        db_session,
        now=FIXED_NOW,
    )
    assert status == 403
    assert payload["code"] == 403


def test_event_handler_rejects_invalid_signature(event_handler, db_session):
    body = json.dumps(_message_event("今日"))
    headers = _signed_headers(body)
    headers["X-Lark-Signature"] = "invalid"
    status, payload = event_handler.handle(body.encode(), headers, db_session, now=FIXED_NOW)
    assert status == 403


def test_event_handler_rejects_replayed_timestamp(event_handler, db_session):
    body = json.dumps(_message_event("今日"))
    old_now = time.time() - 3600
    headers = _signed_headers(body, now=old_now)
    status, payload = event_handler.handle(body.encode(), headers, db_session, now=time.time())
    assert status == 403


def test_event_handler_url_verification(event_handler, db_session):
    body = json.dumps(
        {"type": "url_verification", "token": TEST_TOKEN, "challenge": "challenge-xyz"}
    )
    status, payload = event_handler.handle(
        body.encode(),
        _signed_headers(body),
        db_session,
        now=FIXED_NOW,
    )
    assert status == 200
    assert payload["challenge"] == "challenge-xyz"


def test_event_handler_converts_message_to_command(
    feishu_settings, mock_feishu_client, db_session
):
    class FakeOperationParser:
        def parse(self, text: str, *, source: str, now=None):
            assert text == "今天有啥事"
            return ParsedOperation(
                source=source,
                raw_text=text,
                action_name="query_event",
                payload={
                    "action": "query_event",
                    "source": source,
                    "raw_text": text,
                    "payload": {
                        "filter": {
                            "event_type": "all",
                            "time_range": {
                                "start": "2026-06-07T00:00:00+08:00",
                                "end": "2026-06-08T00:00:00+08:00",
                            },
                            "limit": 20,
                        }
                    },
                },
                confidence=0.9,
                needs_confirmation=False,
            )

    handler = FeishuEventHandler(
        feishu_settings,
        client=mock_feishu_client,
        operation_parser=FakeOperationParser(),
    )
    body = json.dumps(_message_event("今天有啥事"))
    status, payload = handler.handle(
        body.encode(),
        _signed_headers(body),
        db_session,
        now=FIXED_NOW,
    )
    assert status == 200
    assert payload["code"] == 0
    mock_feishu_client.send_text.assert_called_once()
    reply_text = mock_feishu_client.send_text.call_args[0][1]
    assert "事件查询" in reply_text or "暂无" in reply_text
    log = db_session.query(MessageLog).order_by(MessageLog.id.desc()).first()
    assert log is not None
    assert log.raw_content == "今天有啥事"
    assert log.parsed_command == "query_event"
    assert log.reply_status == "ok"


def test_event_handler_unknown_command_returns_help(
    event_handler, mock_feishu_client, db_session
):
    body = json.dumps(_message_event("未知命令"))
    event_handler.handle(body.encode(), _signed_headers(body), db_session, now=FIXED_NOW)
    reply_text = mock_feishu_client.send_text.call_args[0][1]
    assert "可用命令" in reply_text
    assert reply_text == format_help_message()


def test_event_handler_add_assignment_creates_pending_operation(
    event_handler,
    mock_feishu_client,
    db_session,
):
    body = json.dumps(_message_event("添加作业 数学作业 2026-03-05"))

    status, payload = event_handler.handle(
        body.encode(),
        _signed_headers(body),
        db_session,
        now=FIXED_NOW,
    )

    assert status == 200
    assert payload["code"] == 0
    assert db_session.query(Assignment).count() == 0
    pending = db_session.query(PendingOperation).one()
    assert pending.status == PendingOperationStatus.PENDING.value
    assert pending.action_name == "create_event"
    event = pending.operation_payload["payload"]["event"]
    assert event["event_type"] == "deadline"
    assert event["title"] == "数学作业"
    mock_feishu_client.send_interactive_card.assert_called_once()
    card = mock_feishu_client.send_interactive_card.call_args.kwargs["card"]
    serialized = json.dumps(card, ensure_ascii=False)
    assert f"待确认操作 #{pending.id}" in serialized
    assert "数学作业" in serialized
    assert "确认" in serialized
    assert "修改命令" in serialized
    assert "拒绝" in serialized


def test_pending_operation_card_shows_event_and_reminder_times():
    card = build_pending_operation_card(
        operation_id=42,
        raw_text="晚上8点提醒我洗澡",
        action_name="create_event",
        payload={
            "operation": "create",
            "resource": "event",
            "selector": {},
            "fields": {
                "event_type": "life_event",
                "title": "洗澡",
                "scheduled_at": "2026-06-05T20:00:00+08:00",
                "reminder_lead_minutes": 15,
            },
        },
        dashboard_base_url="http://100.65.243.93:8000/dashboard",
    )

    serialized = json.dumps(card, ensure_ascii=False)
    assert "事项：洗澡" in serialized
    assert "计划时间：2026-06-05 20:00" in serialized
    assert "提醒时间：2026-06-05 19:45" in serialized
    assert "提前 15 分钟" in serialized


def test_pending_operation_card_shows_resolved_update_target_and_new_times():
    card = build_pending_operation_card(
        operation_id=43,
        raw_text="把程设作业改到十点",
        action_name="update_event",
        payload={
            "operation": "update",
            "resource": "event",
            "selector": {"event_type": "life_event", "id": 7},
            "selected_candidates": [
                {
                    "event_type": "life_event",
                    "id": 7,
                    "status": "pending",
                    "time_label": "2026-06-06 20:00",
                    "title": "做程序设计作业",
                }
            ],
            "fields": {
                "scheduled_at": "2026-06-06T22:00:00+08:00",
                "reminder_lead_minutes": 15,
            },
        },
        dashboard_base_url="http://100.65.243.93:8000/dashboard",
    )

    serialized = json.dumps(card, ensure_ascii=False)
    assert "将修改：" in serialized
    assert "做程序设计作业" in serialized
    assert "原计划时间：2026-06-06 20:00" in serialized
    assert "新计划时间：2026-06-06 22:00" in serialized
    assert "新提醒时间：2026-06-06 21:45" in serialized
    assert "scheduled_at" not in serialized
    assert "reminder_lead_minutes" not in serialized


def test_event_handler_strips_group_mention_before_parsing_operation(
    event_handler,
    mock_feishu_client,
    db_session,
):
    body = json.dumps(_message_event("@_user_1 添加作业 群聊作业 2026-03-05"))

    status, payload = event_handler.handle(
        body.encode(),
        _signed_headers(body),
        db_session,
        now=FIXED_NOW,
    )

    assert status == 200
    assert payload["code"] == 0
    assert db_session.query(Assignment).count() == 0
    pending = db_session.query(PendingOperation).one()
    assert pending.status == PendingOperationStatus.PENDING.value
    assert pending.action_name == "create_event"
    assert pending.raw_text == "添加作业 群聊作业 2026-03-05"
    assert pending.operation_payload["payload"]["event"]["event_type"] == "deadline"
    assert pending.operation_payload["payload"]["event"]["title"] == "群聊作业"
    mock_feishu_client.send_interactive_card.assert_called_once()


def test_event_handler_confirm_operation_applies_pending_assignment(
    event_handler,
    mock_feishu_client,
    db_session,
):
    body = json.dumps(_message_event("添加作业 数学作业 2026-03-05"))
    event_handler.handle(body.encode(), _signed_headers(body), db_session, now=FIXED_NOW)
    pending = db_session.query(PendingOperation).one()

    callback_body = json.dumps(_card_action_event("confirm_operation", pending.id))
    status, payload = event_handler.handle(
        callback_body.encode(),
        _signed_headers(callback_body),
        db_session,
        now=FIXED_NOW,
    )

    assert status == 200
    assignment = db_session.query(Assignment).filter_by(title="数学作业").one()
    db_session.refresh(pending)
    assert pending.status == PendingOperationStatus.APPLIED.value
    assert pending.result_resource_id == assignment.id
    assert payload["toast"]["type"] == "success"
    assert "已确认" in payload["toast"]["content"]
    assert "数学作业" in payload["toast"]["content"]


def test_event_handler_llm_free_form_message_creates_pending_card(
    feishu_settings,
    mock_feishu_client,
    db_session,
):
    class FakeOperationParser:
        def parse(self, text: str, *, source: str, now=None):
            assert text == "今晚八点提醒我做程设作业"
            return RuleBasedOperationParser(tz=DEFAULT_TZ).parse(
                "添加事项 做程设作业",
                source=source,
            )

    from app.operations.parser import RuleBasedOperationParser

    handler = FeishuEventHandler(
        feishu_settings,
        client=mock_feishu_client,
        operation_parser=FakeOperationParser(),
    )
    body = json.dumps(_message_event("今晚八点提醒我做程设作业"))

    status, payload = handler.handle(
        body.encode(),
        _signed_headers(body),
        db_session,
        now=FIXED_NOW,
    )

    assert status == 200
    assert payload["code"] == 0
    pending = db_session.query(PendingOperation).one()
    assert pending.action_name == "create_event"
    assert pending.operation_payload["payload"]["event"]["event_type"] == "schedule"
    log = db_session.query(MessageLog).order_by(MessageLog.id.desc()).first()
    assert log is not None
    assert log.raw_content == "今晚八点提醒我做程设作业"
    assert log.parsed_command == "create_event"
    assert log.reply_status == "ok"
    mock_feishu_client.send_interactive_card.assert_called_once()


def test_feishu_text_entry_uses_action_result_reply_without_legacy_command_branch(
    feishu_settings,
    mock_feishu_client,
    db_session,
):
    class FakeOperationParser:
        def parse(self, text: str, *, source: str, now=None):
            assert text == "今日"
            return ParsedOperation(
                source=source,
                raw_text=text,
                action_name="query_event",
                payload={
                    "action": "query_event",
                    "source": source,
                    "raw_text": text,
                    "payload": {
                        "filter": {
                            "event_type": "all",
                            "time_range": {
                                "start": "2026-06-07T00:00:00+08:00",
                                "end": "2026-06-08T00:00:00+08:00",
                            },
                            "limit": 20,
                        }
                    },
                },
                confidence=0.9,
                needs_confirmation=False,
            )

    handler = FeishuEventHandler(
        feishu_settings,
        client=mock_feishu_client,
        operation_parser=FakeOperationParser(),
    )
    body = json.dumps(_message_event("今日"))

    status, payload = handler.handle(
        body.encode(),
        _signed_headers(body),
        db_session,
        now=FIXED_NOW,
    )

    assert status == 200
    assert payload["code"] == 0
    reply_text = mock_feishu_client.send_text.call_args[0][1]
    assert "事件查询" in reply_text or "暂无" in reply_text
    log = db_session.query(MessageLog).order_by(MessageLog.id.desc()).first()
    assert log is not None
    assert log.parsed_command == "query_event"
    assert log.action_input["action"] == "query_event"
    assert log.db_result["status"] == "applied"


def test_event_handler_llm_query_event_replies_without_pending_operation(
    feishu_settings,
    mock_feishu_client,
    db_session,
):
    crud.create_assignment(db_session, title="线代作业")
    crud.create_life_event(db_session, title="买电池")

    class FakeOperationParser:
        def parse(self, text: str, *, source: str, now=None):
            assert text == "查一下还有什么事件"
            return ParsedOperation(
                source=source,
                raw_text=text,
                action_name="query_event",
                payload={
                    "operation": "query",
                    "resource": "event",
                    "selector": {},
                    "fields": {"event_type": "all", "status": "open"},
                },
                confidence=0.9,
                needs_confirmation=False,
            )

    handler = FeishuEventHandler(
        feishu_settings,
        client=mock_feishu_client,
        operation_parser=FakeOperationParser(),
    )
    body = json.dumps(_message_event("查一下还有什么事件"))

    status, payload = handler.handle(
        body.encode(),
        _signed_headers(body),
        db_session,
        now=FIXED_NOW,
    )

    assert status == 200
    assert payload["code"] == 0
    assert db_session.query(PendingOperation).count() == 0
    reply_text = mock_feishu_client.send_text.call_args[0][1]
    assert "事件查询" in reply_text
    assert "线代作业" in reply_text
    assert "买电池" in reply_text
    mock_feishu_client.send_interactive_card.assert_not_called()
    log = db_session.query(MessageLog).order_by(MessageLog.id.desc()).first()
    assert log is not None
    assert log.parsed_command == "query_event"
    assert log.reply_status == "ok"


def test_event_handler_two_stage_query_selects_from_compact_candidates(
    feishu_settings,
    mock_feishu_client,
    db_session,
):
    crud.create_life_event(
        db_session,
        title="做程序设计作业",
        scheduled_at=datetime(2026, 6, 6, 20, 0, tzinfo=DEFAULT_TZ),
        notes="长备注不应进入候选短列表",
    )
    crud.create_life_event(
        db_session,
        title="明天跑步",
        scheduled_at=datetime(2026, 6, 7, 20, 0, tzinfo=DEFAULT_TZ),
    )

    class TwoStageParser:
        def __init__(self):
            self.candidates = None

        def parse(self, text: str, *, source: str, now=None):
            assert text == "今晚有啥事"
            return ParsedOperation(
                source=source,
                raw_text=text,
                action_name="query_event",
                payload={
                    "operation": "query",
                    "resource": "event",
                    "selector": {
                        "event_type": "all",
                        "status": "open",
                        "time_range": {
                            "start": "2026-06-06T18:00:00+08:00",
                            "end": "2026-06-07T00:00:00+08:00",
                        },
                        "target_description": "今晚事项",
                        "max_candidates": 10,
                    },
                    "fields": {},
                },
                confidence=0.9,
                needs_confirmation=False,
            )

        def select_candidates(self, *, raw_text, parsed, candidates):
            assert raw_text == "今晚有啥事"
            assert parsed.action_name == "query_event"
            self.candidates = candidates
            assert len(candidates) == 1
            assert candidates[0]["ref"] == "c1"
            assert candidates[0]["event_type"] == "schedule"
            assert candidates[0]["title"] == "做程序设计作业"
            assert "id" not in candidates[0]
            return {
                "match_status": "single",
                "selected_refs": ["c1"],
                "confidence": 0.93,
                "reason": "今晚唯一候选",
            }

    parser = TwoStageParser()
    handler = FeishuEventHandler(
        feishu_settings,
        client=mock_feishu_client,
        operation_parser=parser,
    )
    body = json.dumps(_message_event("今晚有啥事"))

    status, payload = handler.handle(
        body.encode(),
        _signed_headers(body),
        db_session,
        now=FIXED_NOW,
    )

    assert status == 200
    assert payload["code"] == 0
    assert db_session.query(PendingOperation).count() == 0
    reply_text = mock_feishu_client.send_text.call_args[0][1]
    assert "做程序设计作业" in reply_text
    assert "明天跑步" not in reply_text
    assert "长备注" not in reply_text


def test_event_handler_two_stage_update_resolves_candidate_before_pending(
    feishu_settings,
    mock_feishu_client,
    db_session,
):
    target = crud.create_life_event(
        db_session,
        title="做程序设计作业",
        scheduled_at=datetime(2026, 6, 6, 20, 0, tzinfo=DEFAULT_TZ),
    )
    other = crud.create_life_event(
        db_session,
        title="写英语作业",
        scheduled_at=datetime(2026, 6, 6, 20, 30, tzinfo=DEFAULT_TZ),
    )

    class TwoStageParser:
        def parse(self, text: str, *, source: str, now=None):
            assert text == "把做程序设计作业改到今晚九点"
            return ParsedOperation(
                source=source,
                raw_text=text,
                action_name="update_event",
                payload={
                    "operation": "update",
                    "resource": "event",
                    "selector": {
                        "event_type": "life_event",
                        "status": "open",
                        "time_range": {
                            "start": "2026-06-06T18:00:00+08:00",
                            "end": "2026-06-07T00:00:00+08:00",
                        },
                        "target_description": "做程序设计作业",
                        "max_candidates": 10,
                    },
                    "fields": {"scheduled_at": "2026-06-06T21:00:00+08:00"},
                },
                confidence=0.9,
                needs_confirmation=True,
            )

        def select_candidates(self, *, raw_text, parsed, candidates):
            assert {item["title"] for item in candidates} == {
                "做程序设计作业",
                "写英语作业",
            }
            ref = next(item["ref"] for item in candidates if item["title"] == "做程序设计作业")
            return {
                "match_status": "single",
                "selected_refs": [ref],
                "confidence": 0.94,
                "reason": "标题语义匹配",
            }

    handler = FeishuEventHandler(
        feishu_settings,
        client=mock_feishu_client,
        operation_parser=TwoStageParser(),
    )
    body = json.dumps(_message_event("把做程序设计作业改到今晚九点"))

    status, payload = handler.handle(
        body.encode(),
        _signed_headers(body),
        db_session,
        now=FIXED_NOW,
    )

    assert status == 200
    assert payload["code"] == 0
    db_session.refresh(target)
    db_session.refresh(other)
    target_scheduled_at = target.scheduled_at
    other_scheduled_at = other.scheduled_at
    if target_scheduled_at is not None and target_scheduled_at.tzinfo is None:
        target_scheduled_at = target_scheduled_at.replace(tzinfo=DEFAULT_TZ)
    if other_scheduled_at is not None and other_scheduled_at.tzinfo is None:
        other_scheduled_at = other_scheduled_at.replace(tzinfo=DEFAULT_TZ)
    assert target_scheduled_at == datetime(2026, 6, 6, 20, 0, tzinfo=DEFAULT_TZ)
    assert other_scheduled_at == datetime(2026, 6, 6, 20, 30, tzinfo=DEFAULT_TZ)
    pending = db_session.query(PendingOperation).one()
    assert pending.action_name == "update_event"
    resolved = pending.operation_payload["payload"]
    assert resolved["selector"]["event_type"] == "life_event"
    assert resolved["selector"]["id"] == target.id
    assert resolved["patch"]["start_at"] == "2026-06-06T21:00:00+08:00"
    mock_feishu_client.send_interactive_card.assert_called_once()


def test_event_handler_two_stage_does_not_fallback_from_legacy_selected_ids(
    feishu_settings,
    mock_feishu_client,
    db_session,
):
    crud.create_life_event(
        db_session,
        title="劳动法律法规考试",
        scheduled_at=datetime(2026, 6, 6, 21, 0, tzinfo=DEFAULT_TZ),
    )

    class LegacyIdParser:
        def parse(self, text: str, *, source: str, now=None):
            return ParsedOperation(
                source=source,
                raw_text=text,
                action_name="update_event",
                payload={
                    "action": "update_event",
                    "source": source,
                    "raw_text": text,
                    "payload": {
                        "selector": {
                            "mode": "semantic_ref",
                            "refs": [],
                            "filter": {
                                "event_type": "all",
                                "time_range": {
                                    "start": "2026-06-06T18:00:00+08:00",
                                    "end": "2026-06-07T00:00:00+08:00",
                                },
                            },
                            "target_description": "劳动法律法规考试",
                        },
                        "patch": {"start_at": "2026-06-06T22:00:00+08:00"},
                    },
                },
                confidence=0.9,
                needs_confirmation=True,
            )

        def select_candidates(self, *, raw_text, parsed, candidates):
            assert candidates
            return {
                "match_status": "single",
                "selected_ids": [{"event_type": "life_event", "id": 999}],
                "confidence": 0.99,
                "reason": "旧协议输出，应该被拒绝",
            }

    handler = FeishuEventHandler(
        feishu_settings,
        client=mock_feishu_client,
        operation_parser=LegacyIdParser(),
    )
    body = json.dumps(_message_event("把劳动法律法规考试调整到十点"))

    status, payload = handler.handle(
        body.encode(),
        _signed_headers(body),
        db_session,
        now=FIXED_NOW,
    )

    assert status == 200
    assert payload["code"] == 0
    mock_feishu_client.send_text.assert_called_once()
    assert "无法确定" in mock_feishu_client.send_text.call_args[0][1]
    assert db_session.query(PendingOperation).count() == 0


def test_event_handler_two_stage_uses_all_event_types_when_parser_overfilters(
    feishu_settings,
    mock_feishu_client,
    db_session,
):
    target = crud.create_life_event(
        db_session,
        title="考一下劳动法律法规",
        scheduled_at=datetime(2026, 6, 7, 21, 0, tzinfo=DEFAULT_TZ),
    )
    crud.create_life_event(
        db_session,
        title="1111",
        scheduled_at=datetime(2026, 6, 7, 20, 0, tzinfo=DEFAULT_TZ),
    )
    crud.create_assignment(
        db_session,
        title="晚上的考试",
        due_at=datetime(2026, 6, 7, 20, 30, tzinfo=DEFAULT_TZ),
    )

    class OverfilteredParser:
        def __init__(self):
            self.seen_candidates: list[list[dict[str, Any]]] = []

        def parse(self, text: str, *, source: str, now=None):
            assert text == "把晚上的劳动法律法规考试调整到10点"
            return ParsedOperation(
                source=source,
                raw_text=text,
                action_name="update_event",
                payload={
                    "operation": "update",
                    "resource": "event",
                    "selector": {
                        "event_type": "assignment",
                        "status": "open",
                        "time_range": {
                            "start": "2026-06-07T18:00:00+08:00",
                            "end": "2026-06-08T00:00:00+08:00",
                        },
                        "target_description": "劳动法律法规考试",
                        "max_candidates": 10,
                    },
                    "fields": {"scheduled_at": "2026-06-07T22:00:00+08:00"},
                },
                confidence=0.9,
                needs_confirmation=True,
            )

        def select_candidates(self, *, raw_text, parsed, candidates):
            self.seen_candidates.append(candidates)
            assert {item["title"] for item in candidates} == {
                "考一下劳动法律法规",
                "1111",
                "晚上的考试",
            }
            ref = next(
                item["ref"] for item in candidates if item["title"] == "考一下劳动法律法规"
            )
            return {
                "match_status": "single",
                "selected_refs": [ref],
                "confidence": 0.95,
                "reason": "劳动法律法规考试语义匹配",
            }

    parser = OverfilteredParser()
    handler = FeishuEventHandler(
        feishu_settings,
        client=mock_feishu_client,
        operation_parser=parser,
    )
    body = json.dumps(_message_event("把晚上的劳动法律法规考试调整到10点"))

    status, payload = handler.handle(
        body.encode(),
        _signed_headers(body),
        db_session,
        now=FIXED_NOW,
    )

    assert status == 200
    assert payload["code"] == 0
    assert len(parser.seen_candidates) == 1
    pending = db_session.query(PendingOperation).one()
    assert pending.action_name == "update_event"
    resolved = pending.operation_payload["payload"]
    assert resolved["selector"]["event_type"] == "life_event"
    assert resolved["selector"]["id"] == target.id
    serialized_card = json.dumps(
        mock_feishu_client.send_interactive_card.call_args.kwargs["card"],
        ensure_ascii=False,
    )
    assert "考一下劳动法律法规" in serialized_card
    assert "1111" not in serialized_card


def test_event_handler_two_stage_delete_all_creates_batch_pending(
    feishu_settings,
    mock_feishu_client,
    db_session,
):
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

    class TwoStageParser:
        def parse(self, text: str, *, source: str, now=None):
            assert text == "删除今晚的所有事项"
            return ParsedOperation(
                source=source,
                raw_text=text,
                action_name="delete_event",
                payload={
                    "operation": "delete",
                    "resource": "event",
                    "selector": {
                        "event_type": "life_event",
                        "status": "open",
                        "time_range": {
                            "start": "2026-06-06T18:00:00+08:00",
                            "end": "2026-06-07T00:00:00+08:00",
                        },
                        "target_description": "今晚的所有事项",
                        "max_candidates": 20,
                    },
                    "fields": {},
                },
                confidence=0.9,
                needs_confirmation=True,
            )

        def select_candidates(self, *, raw_text, parsed, candidates):
            assert {item["title"] for item in candidates} == {"今晚事项 A", "今晚事项 B"}
            refs = [item["ref"] for item in candidates]
            return {
                "match_status": "multiple",
                "selected_refs": refs,
                "confidence": 0.96,
                "reason": "用户明确要求删除今晚所有事项",
            }

    handler = FeishuEventHandler(
        feishu_settings,
        client=mock_feishu_client,
        operation_parser=TwoStageParser(),
    )
    body = json.dumps(_message_event("删除今晚的所有事项"))

    status, payload = handler.handle(
        body.encode(),
        _signed_headers(body),
        db_session,
        now=FIXED_NOW,
    )

    assert status == 200
    assert payload["code"] == 0
    pending = db_session.query(PendingOperation).one()
    assert pending.action_name == "delete_event"
    assert pending.operation_payload["payload"]["selector"]["targets"] == [
        {"event_type": "life_event", "id": first.id},
        {"event_type": "life_event", "id": second.id},
    ]
    db_session.refresh(first)
    db_session.refresh(second)
    db_session.refresh(tomorrow)
    assert first.status == "pending"
    assert second.status == "pending"
    assert tomorrow.status == "pending"
    serialized_card = json.dumps(
        mock_feishu_client.send_interactive_card.call_args.kwargs["card"],
        ensure_ascii=False,
    )
    assert "今晚事项 A" in serialized_card
    assert "今晚事项 B" in serialized_card
    assert "明晚事项" not in serialized_card


def test_event_handler_ignores_duplicate_free_form_message_id(
    feishu_settings,
    mock_feishu_client,
    db_session,
):
    class FakeOperationParser:
        def parse(self, text: str, *, source: str, now=None):
            assert text == "晚上8点提醒我洗澡"
            return RuleBasedOperationParser(tz=DEFAULT_TZ).parse(
                "添加事项 洗澡",
                source=source,
            )

    from app.operations.parser import RuleBasedOperationParser

    handler = FeishuEventHandler(
        feishu_settings,
        client=mock_feishu_client,
        operation_parser=FakeOperationParser(),
    )
    body = json.dumps(_message_event("晚上8点提醒我洗澡", message_id="om_duplicate"))

    first_status, first_payload = handler.handle(
        body.encode(),
        _signed_headers(body),
        db_session,
        now=FIXED_NOW,
    )
    second_status, second_payload = handler.handle(
        body.encode(),
        _signed_headers(body),
        db_session,
        now=FIXED_NOW,
    )

    assert first_status == 200
    assert first_payload["code"] == 0
    assert second_status == 200
    assert second_payload == {"code": 0, "msg": "duplicate message ignored"}
    assert db_session.query(PendingOperation).count() == 1
    assert db_session.query(MessageLog).filter_by(external_message_id="om_duplicate").count() == 1
    mock_feishu_client.send_interactive_card.assert_called_once()


def test_event_handler_ignores_duplicate_read_message_id(
    feishu_settings,
    mock_feishu_client,
    db_session,
):
    class FakeOperationParser:
        def parse(self, text: str, *, source: str, now=None):
            return ParsedOperation(
                source=source,
                raw_text=text,
                action_name="query_event",
                payload={
                    "action": "query_event",
                    "source": source,
                    "raw_text": text,
                    "payload": {"filter": {"event_type": "all", "limit": 20}},
                },
                confidence=0.9,
                needs_confirmation=False,
            )

    handler = FeishuEventHandler(
        feishu_settings,
        client=mock_feishu_client,
        operation_parser=FakeOperationParser(),
    )
    body = json.dumps(_message_event("今日", message_id="om_today_duplicate"))

    handler.handle(body.encode(), _signed_headers(body), db_session, now=FIXED_NOW)
    status, payload = handler.handle(
        body.encode(),
        _signed_headers(body),
        db_session,
        now=FIXED_NOW,
    )

    assert status == 200
    assert payload == {"code": 0, "msg": "duplicate message ignored"}
    assert (
        db_session.query(MessageLog)
        .filter_by(external_message_id="om_today_duplicate")
        .count()
        == 1
    )
    mock_feishu_client.send_text.assert_called_once()


def test_event_handler_reject_operation_does_not_apply(
    event_handler,
    mock_feishu_client,
    db_session,
):
    body = json.dumps(_message_event("添加事项 洗衣服"))
    event_handler.handle(body.encode(), _signed_headers(body), db_session, now=FIXED_NOW)
    pending = db_session.query(PendingOperation).one()

    callback_body = json.dumps(_card_action_event("reject_operation", pending.id))
    status, payload = event_handler.handle(
        callback_body.encode(),
        _signed_headers(callback_body),
        db_session,
        now=FIXED_NOW,
    )

    assert status == 200
    assert db_session.query(LifeEvent).count() == 0
    db_session.refresh(pending)
    assert pending.status == PendingOperationStatus.REJECTED.value
    assert payload["toast"]["type"] == "success"
    assert "已拒绝" in payload["toast"]["content"]


def test_event_handler_card_confirm_callback_applies_pending_operation_and_deletes_card(
    event_handler,
    mock_feishu_client,
    db_session,
):
    body = json.dumps(_message_event("添加事项 做程设作业"))
    event_handler.handle(body.encode(), _signed_headers(body), db_session, now=FIXED_NOW)
    pending = db_session.query(PendingOperation).one()

    callback_body = json.dumps(_card_action_event("confirm_operation", pending.id))
    status, payload = event_handler.handle(
        callback_body.encode(),
        _signed_headers(callback_body),
        db_session,
        now=FIXED_NOW,
    )

    event = db_session.query(LifeEvent).filter_by(title="做程设作业").one()
    db_session.refresh(pending)
    assert status == 200
    assert pending.status == PendingOperationStatus.APPLIED.value
    assert pending.result_resource_id == event.id
    assert payload["toast"]["type"] == "success"
    assert "已确认" in payload["toast"]["content"]
    mock_feishu_client.delete_message.assert_called_once_with("om_card_1")


def test_event_handler_card_reject_callback_rejects_pending_operation_and_deletes_card(
    event_handler,
    mock_feishu_client,
    db_session,
):
    body = json.dumps(_message_event("添加事项 做程设作业"))
    event_handler.handle(body.encode(), _signed_headers(body), db_session, now=FIXED_NOW)
    pending = db_session.query(PendingOperation).one()

    callback_body = json.dumps(_card_action_event("reject_operation", pending.id))
    status, payload = event_handler.handle(
        callback_body.encode(),
        _signed_headers(callback_body),
        db_session,
        now=FIXED_NOW,
    )

    db_session.refresh(pending)
    assert status == 200
    assert pending.status == PendingOperationStatus.REJECTED.value
    assert db_session.query(LifeEvent).count() == 0
    assert payload["toast"]["type"] == "success"
    assert "已拒绝" in payload["toast"]["content"]
    mock_feishu_client.delete_message.assert_called_once_with("om_card_1")


def test_event_handler_confirm_invalid_operation_replies_without_crashing(
    event_handler,
    mock_feishu_client,
    db_session,
):
    callback_body = json.dumps(_card_action_event("confirm_operation", 999))
    status, payload = event_handler.handle(
        callback_body.encode(),
        _signed_headers(callback_body),
        db_session,
        now=FIXED_NOW,
    )

    assert status == 200
    assert payload["toast"]["type"] == "error"
    assert "未找到" in payload["toast"]["content"] or "无法确认" in payload["toast"]["content"]


def test_feishu_route_integration(feishu_settings, mock_feishu_client, db_session):
    from app.db.session import get_db
    from app.feishu.event_handler import create_feishu_router

    app = FastAPI()
    app.include_router(
        create_feishu_router(
            FeishuEventHandler(feishu_settings, client=mock_feishu_client),
        )
    )
    app.dependency_overrides[get_db] = lambda: db_session

    client = TestClient(app)
    body = json.dumps(_message_event("帮助"))
    now = time.time()
    response = client.post(
        "/feishu/event",
        content=body,
        headers=_signed_headers(body, now=now),
    )
    assert response.status_code == 200
    assert response.json()["code"] == 0
    mock_feishu_client.send_text.assert_called_once()


def test_feishu_client_send_text_uses_mock_transport():
    token_requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_requests
        if request.url.path.endswith("/tenant_access_token/internal"):
            token_requests += 1
            return httpx.Response(200, json={"code": 0, "tenant_access_token": "t-token"})
        return httpx.Response(200, json={"code": 0, "data": {"message_id": "msg_1"}})

    transport = httpx.MockTransport(handler)
    client = FeishuClient("app", "secret", transport=transport)
    result = client.send_text("oc_chat", "hello")
    assert result["code"] == 0
    result = client.send_text("oc_chat", "hello again")
    assert result["code"] == 0
    assert token_requests == 1


def test_feishu_client_delete_message_uses_message_delete_api():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/tenant_access_token/internal"):
            return httpx.Response(200, json={"code": 0, "tenant_access_token": "t-token"})
        return httpx.Response(200, json={"code": 0})

    transport = httpx.MockTransport(handler)
    client = FeishuClient("app", "secret", transport=transport)

    result = client.delete_message("om_card_1")

    assert result == {"code": 0}
    delete_request = requests[-1]
    assert delete_request.method == "DELETE"
    assert delete_request.url.path == "/open-apis/im/v1/messages/om_card_1"
    assert delete_request.headers["Authorization"] == "Bearer t-token"


def test_feishu_client_refreshes_token_on_send_auth_error():
    token_requests = 0
    send_requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_requests, send_requests
        if request.url.path.endswith("/tenant_access_token/internal"):
            token_requests += 1
            return httpx.Response(
                200,
                json={"code": 0, "tenant_access_token": f"t-token-{token_requests}"},
            )
        send_requests += 1
        if send_requests == 1:
            return httpx.Response(401, json={"code": 99991663, "msg": "token expired"})
        assert request.headers["Authorization"] == "Bearer t-token-2"
        return httpx.Response(200, json={"code": 0, "data": {"message_id": "msg_1"}})

    transport = httpx.MockTransport(handler)
    client = FeishuClient("app", "secret", transport=transport)
    result = client.send_text("oc_chat", "hello")
    assert result["code"] == 0
    assert token_requests == 2
    assert send_requests == 2
