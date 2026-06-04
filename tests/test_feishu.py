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
from app.feishu.client import FeishuClient
from app.feishu.commands import (
    COMMAND_ADD_ASSIGNMENT,
    COMMAND_COMPLETE,
    COMMAND_HELP,
    COMMAND_TODAY,
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
    assert parse_command("本周DDL").name == COMMAND_WEEKLY_DDL
    assert parse_command("添加作业 数学作业 2026-03-05").name == COMMAND_ADD_ASSIGNMENT
    assert parse_command("添加事项 洗衣服").name == "add_life_event"
    assert parse_command("完成 数学作业").name == COMMAND_COMPLETE
    assert parse_command("帮助").name == COMMAND_HELP


def test_parse_command_unknown_returns_help():
    assert parse_command("随便说点什么").name == COMMAND_HELP


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
    event_handler, mock_feishu_client, db_session
):
    body = json.dumps(_message_event("今日"))
    status, payload = event_handler.handle(
        body.encode(),
        _signed_headers(body),
        db_session,
        now=FIXED_NOW,
    )
    assert status == 200
    assert payload["code"] == 0
    mock_feishu_client.send_text.assert_called_once()
    reply_text = mock_feishu_client.send_text.call_args[0][1]
    assert "今日晨报" in reply_text


def test_event_handler_unknown_command_returns_help(
    event_handler, mock_feishu_client, db_session
):
    body = json.dumps(_message_event("未知命令"))
    event_handler.handle(body.encode(), _signed_headers(body), db_session, now=FIXED_NOW)
    reply_text = mock_feishu_client.send_text.call_args[0][1]
    assert "可用命令" in reply_text
    assert reply_text == format_help_message()


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
