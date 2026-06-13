from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import crud
from app.main import create_app
from app.secretary.rules import DEFAULT_TZ


def _client(monkeypatch) -> TestClient:
    monkeypatch.setenv("AGENT_API_TOKEN", "agent-secret")
    get_settings.cache_clear()
    return TestClient(create_app())


def test_agent_tools_requires_token(monkeypatch) -> None:
    client = _client(monkeypatch)

    response = client.get("/agent/tools")

    assert response.status_code == 401


def test_agent_tools_manifest_exposes_openclaw_contract(monkeypatch) -> None:
    client = _client(monkeypatch)

    response = client.get(
        "/agent/tools",
        headers={"X-SmartCore-Agent-Token": "agent-secret"},
    )

    assert response.status_code == 200
    tools = response.json()["tools"]
    by_name = {tool["name"]: tool for tool in tools}
    assert by_name["query_events"]["endpoint"] == "/agent/db/query_events"
    assert by_name["query_events"]["risk"] == "read"
    assert by_name["query_events"]["confirmation_required"] is False
    for required in (
        "query_events",
        "create_event",
        "update_event",
        "delete_event",
        "send_text",
        "send_query_result_card",
        "send_operation_success_card",
        "send_reminder_card",
    ):
        assert required in by_name
        assert by_name[required]["input_schema"]

    assert by_name["create_event"]["endpoint"] == "/agent/db/create_event"
    assert by_name["create_event"]["confirmation_required"] is True
    assert by_name["update_event"]["endpoint"] == "/agent/db/update_event"
    assert by_name["delete_event"]["risk"] == "destructive"
    assert by_name["send_text"]["endpoint"] == "/agent/feedback/send_text"
    assert by_name["send_query_result_card"]["endpoint"] == (
        "/agent/feedback/send_query_result_card"
    )
    assert by_name["send_operation_success_card"]["endpoint"] == (
        "/agent/feedback/send_operation_success_card"
    )
    assert by_name["send_reminder_card"]["endpoint"] == "/agent/feedback/send_reminder_card"
    assert by_name["query_events"]["input_schema"]["filter"]["time_range"] == {
        "start": "ISO-8601",
        "end": "ISO-8601",
    }


def test_agent_create_update_delete_events_return_pending_confirmation(
    db_session, monkeypatch
) -> None:
    life_event = crud.create_life_event(
        db_session,
        title="晚自习",
        scheduled_at=datetime(2026, 6, 12, 20, 0, tzinfo=DEFAULT_TZ),
    )
    client = _client(monkeypatch)
    headers = {"X-SmartCore-Agent-Token": "agent-secret"}

    create_response = client.post(
        "/agent/db/create_event",
        headers=headers,
        json={
            "payload": {
                "event": {
                    "event_type": "schedule",
                    "title": "OpenClaw 联调",
                    "start_at": "2026-06-12T21:00:00+08:00",
                }
            },
            "source_event_id": "feishu:om_create",
            "raw_text": "今晚九点联调 OpenClaw",
        },
    )
    update_response = client.post(
        "/agent/db/update_event",
        headers=headers,
        json={
            "payload": {
                "selector": {"event_type": "schedule", "id": life_event.id},
                "patch": {"title": "晚自习复盘"},
            },
            "source_event_id": "feishu:om_update",
            "raw_text": "把晚自习改成复盘",
        },
    )
    delete_response = client.post(
        "/agent/db/delete_event",
        headers=headers,
        json={
            "payload": {"selector": {"event_type": "schedule", "id": life_event.id}},
            "source_event_id": "feishu:om_delete",
            "raw_text": "取消晚自习",
        },
    )

    for response in (create_response, update_response, delete_response):
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        assert body["status"] == "pending_confirmation"
        assert body["operation_id"] is not None


def test_agent_query_events_uses_action_executor_contract(db_session, monkeypatch) -> None:
    crud.create_life_event(
        db_session,
        title="OpenClaw 架构设计",
        scheduled_at=datetime(2026, 6, 12, 20, 0, tzinfo=DEFAULT_TZ),
    )
    client = _client(monkeypatch)

    response = client.post(
        "/agent/db/query_events",
        headers={"X-SmartCore-Agent-Token": "agent-secret"},
        json={
            "filter": {
                "event_type": "all",
                "status": ["pending", "active"],
                "limit": 10,
                "time_range": {
                    "start": "2026-06-12T00:00:00+08:00",
                    "end": "2026-06-13T00:00:00+08:00",
                },
            },
            "source_event_id": "feishu:om_test",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["action"] == "query_event"
    assert body["data"]["events"][0]["title"] == "OpenClaw 架构设计"


def test_agent_query_events_supports_keyword_filter(db_session, monkeypatch) -> None:
    crud.create_life_event(
        db_session,
        title="Linux 实验",
        scheduled_at=datetime(2026, 6, 12, 20, 0, tzinfo=DEFAULT_TZ),
    )
    crud.create_life_event(
        db_session,
        title="英语阅读",
        scheduled_at=datetime(2026, 6, 12, 21, 0, tzinfo=DEFAULT_TZ),
    )
    client = _client(monkeypatch)

    response = client.post(
        "/agent/db/query_events",
        headers={"X-SmartCore-Agent-Token": "agent-secret"},
        json={
            "filter": {
                "event_type": "all",
                "status": ["pending", "active"],
                "keyword": "linux",
                "time_range": {
                    "start": "2026-06-12T00:00:00+08:00",
                    "end": "2026-06-13T00:00:00+08:00",
                },
            },
        },
    )

    assert response.status_code == 200
    events = response.json()["data"]["events"]
    assert [item["title"] for item in events] == ["Linux 实验"]


def test_agent_create_event_returns_pending_confirmation(db_session, monkeypatch) -> None:
    client = _client(monkeypatch)

    response = client.post(
        "/agent/db/create_event",
        headers={"X-SmartCore-Agent-Token": "agent-secret"},
        json={
            "payload": {
                "event": {
                    "event_type": "schedule",
                    "title": "OpenClaw 联调",
                    "start_at": "2026-06-12T20:00:00+08:00",
                }
            },
            "source_event_id": "feishu:om_create",
            "raw_text": "今晚八点联调 OpenClaw",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["action"] == "create_event"
    assert body["status"] == "pending_confirmation"
    assert body["operation_id"] is not None


def test_agent_feedback_send_text_uses_feishu(monkeypatch) -> None:
    sent: dict[str, Any] = {}

    class FakeFeishuClient:
        def __init__(self, app_id: str, app_secret: str) -> None:
            sent["app_id"] = app_id
            sent["app_secret"] = app_secret

        def send_text(self, chat_id: str, text: str):
            sent["chat_id"] = chat_id
            sent["text"] = text
            return {"code": 0}

    monkeypatch.setenv("FEISHU_APP_ID", "app-id")
    monkeypatch.setenv("FEISHU_APP_SECRET", "app-secret")
    client = _client(monkeypatch)
    monkeypatch.setattr("app.agent.routes.FeishuClient", FakeFeishuClient)

    response = client.post(
        "/agent/feedback/send_text",
        headers={"X-SmartCore-Agent-Token": "agent-secret"},
        json={"target": {"chat_id": "oc_chat"}, "text": "已处理"},
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert sent["chat_id"] == "oc_chat"
    assert sent["text"] == "已处理"


def test_agent_feedback_send_query_result_card_uses_feishu_card(monkeypatch) -> None:
    sent: dict[str, Any] = {}

    class FakeFeishuClient:
        def __init__(self, app_id: str, app_secret: str) -> None:
            sent["app_id"] = app_id
            sent["app_secret"] = app_secret

        def send_interactive_card(self, chat_id: str, *, card: dict[str, Any]):
            sent["chat_id"] = chat_id
            sent["card"] = card
            return {"code": 0}

    monkeypatch.setenv("FEISHU_APP_ID", "app-id")
    monkeypatch.setenv("FEISHU_APP_SECRET", "app-secret")
    client = _client(monkeypatch)
    monkeypatch.setattr("app.agent.routes.FeishuClient", FakeFeishuClient)

    response = client.post(
        "/agent/feedback/send_query_result_card",
        headers={"X-SmartCore-Agent-Token": "agent-secret"},
        json={
            "target": {"chat_id": "oc_chat"},
            "data": {
                "events": [
                    {
                        "event_type": "course",
                        "title": "Linux 操作系统",
                        "time_label": "2026-06-12 18:30-21:00",
                        "location": "实验楼 302",
                    }
                ]
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert sent["chat_id"] == "oc_chat"
    serialized = str(sent["card"])
    assert "事件查询" in serialized
    assert "Linux 操作系统" in serialized


def test_agent_feedback_send_operation_success_card(monkeypatch) -> None:
    sent: dict[str, Any] = {}

    class FakeFeishuClient:
        def __init__(self, app_id: str, app_secret: str) -> None:
            pass

        def send_interactive_card(self, chat_id: str, *, card: dict[str, Any]):
            sent["chat_id"] = chat_id
            sent["card"] = card
            return {"code": 0}

    client = _client(monkeypatch)
    monkeypatch.setattr("app.agent.routes.FeishuClient", FakeFeishuClient)

    response = client.post(
        "/agent/feedback/send_operation_success_card",
        headers={"X-SmartCore-Agent-Token": "agent-secret"},
        json={
            "target": {"chat_id": "oc_chat"},
            "data": {
                "action_name": "create_event",
                "payload": {
                    "action": "create_event",
                    "payload": {
                        "event": {
                            "event_type": "schedule",
                            "title": "读论文",
                        }
                    },
                },
            },
        },
    )

    assert response.status_code == 200
    serialized = str(sent["card"])
    assert "操作成功" in serialized
    assert "读论文" in serialized


def test_agent_feedback_send_reminder_card_round_trips_actions(monkeypatch) -> None:
    sent: dict[str, Any] = {}

    class FakeFeishuClient:
        def __init__(self, app_id: str, app_secret: str) -> None:
            pass

        def send_interactive_card(self, chat_id: str, *, card: dict[str, Any]):
            sent["chat_id"] = chat_id
            sent["card"] = card
            return {"code": 0}

    client = _client(monkeypatch)
    monkeypatch.setattr("app.agent.routes.FeishuClient", FakeFeishuClient)

    response = client.post(
        "/agent/feedback/send_reminder_card",
        headers={"X-SmartCore-Agent-Token": "agent-secret"},
        json={
            "target": {"chat_id": "oc_chat"},
            "data": {
                "title": "Linux 实验",
                "event_type": "course",
                "scheduled_label": "2026-06-12 19:00-21:00",
                "minutes_until": 30,
                "event_id": "course:12",
            },
        },
    )

    assert response.status_code == 200
    serialized = str(sent["card"])
    assert "Linux 实验" in serialized
    assert "complete_event" in serialized
    assert "delay_event" in serialized
