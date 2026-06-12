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
    assert by_name["send_query_result_card"]["endpoint"] == (
        "/agent/feedback/send_query_result_card"
    )
    assert by_name["send_reminder_card"]["endpoint"] == "/agent/feedback/send_reminder_card"


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
