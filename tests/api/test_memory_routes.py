from __future__ import annotations

import json
import sqlite3

import httpx
import pytest

from app.server.api import assistant_routes
from app.server.config import get_settings
from app.server.db.session import init_db

pytestmark = pytest.mark.api


def _stream_stub(monkeypatch, captured: dict[str, object], reply: str = "好的，记住了") -> None:
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def raise_for_status(self) -> None:
            return None

        def iter_lines(self):
            yield "data: " + json.dumps({"type": "message", "text": reply, "mode": "new"})
            yield ""
            yield "data: " + json.dumps({"type": "done", "sessionId": "s1", "response": reply})
            yield ""

    def stream(method: str, url: str, **kwargs: object) -> Response:
        captured.setdefault("events", []).append(kwargs["json"])
        return Response()

    monkeypatch.setattr(httpx, "stream", stream)


def test_memory_crud_is_owner_scoped(signed_client_factory) -> None:
    client = signed_client_factory("default")

    created = client.post("/api/memory", json={"content": "我对花生过敏", "type": "fact"})
    assert created.status_code == 200
    item = created.json()["data"]
    assert item["content"] == "用户对花生过敏"
    assert item["source"] == "user_explicit"

    listed = client.get("/api/memory").json()["data"]
    assert listed["enabled"] is True
    assert [row["memoryId"] for row in listed["items"]] == [item["memoryId"]]
    assert {row["value"] for row in listed["types"]} >= {"profile", "preference", "fact"}

    edited = client.patch(
        f"/api/memory/{item['memoryId']}", json={"content": "用户对花生和芒果过敏", "type": "profile"}
    )
    assert edited.status_code == 200
    assert edited.json()["data"]["type"] == "profile"

    assert client.patch(f"/api/memory/{item['memoryId']}", json={"type": "bogus"}).status_code == 422
    assert client.post("/api/memory", json={"content": "我的密码是 abc123"}).status_code == 422

    deleted = client.delete(f"/api/memory/{item['memoryId']}")
    assert deleted.status_code == 200
    assert client.get("/api/memory").json()["data"]["items"] == []
    assert client.delete(f"/api/memory/{item['memoryId']}").status_code == 404


def test_memory_requires_login(client) -> None:
    assert client.get("/api/memory").status_code == 401
    assert client.post("/api/memory", json={"content": "x"}).status_code == 401


def test_stream_remembers_explicitly_and_injects_next_turn(signed_client_factory, monkeypatch) -> None:
    monkeypatch.setenv("DSH_EVENTS_ENDPOINT", "http://dsh.local/api/smartcore/events")
    monkeypatch.setenv("DSH_EVENTS_TOKEN", "dsh-token")
    get_settings.cache_clear()
    scheduled: list[dict[str, object]] = []
    monkeypatch.setattr(
        assistant_routes, "schedule_extraction", lambda **kwargs: scheduled.append(kwargs) or True
    )
    captured: dict[str, object] = {}
    _stream_stub(monkeypatch, captured)
    client = signed_client_factory("default")

    first = client.post("/api/assistant/stream", json={"text": "记住我喜欢早上处理难的任务"})
    assert first.status_code == 200 and '"type": "done"' in first.text
    first_event = captured["events"][0]
    assert first_event["memoryEnabled"] is True
    assert "用户喜欢早上处理难的任务" in first_event["memoryAction"]
    assert "[偏好] 用户喜欢早上处理难的任务" in first_event["userMemory"]
    # An explicit command is already stored; no extra LLM extraction.
    assert scheduled == []

    items = client.get("/api/memory").json()["data"]["items"]
    assert [row["content"] for row in items] == ["用户喜欢早上处理难的任务"]

    second = client.post("/api/assistant/stream", json={"text": "明天早上我先做什么任务比较好？"})
    assert second.status_code == 200
    second_event = captured["events"][1]
    assert "[偏好] 用户喜欢早上处理难的任务" in second_event["userMemory"]
    assert "memoryAction" not in second_event
    assert len(scheduled) == 1
    assert scheduled[0]["user_id"] == "default"
    assert scheduled[0]["assistant_text"] == "好的，记住了"

    third = client.post("/api/assistant/stream", json={"text": "忘掉我喜欢早上处理难的任务"})
    assert third.status_code == 200
    assert "已从长期记忆删除" in captured["events"][2]["memoryAction"]
    assert client.get("/api/memory").json()["data"]["items"] == []


def test_memory_flag_disables_injection(signed_client_factory, monkeypatch) -> None:
    monkeypatch.setenv("DSH_EVENTS_ENDPOINT", "http://dsh.local/api/smartcore/events")
    monkeypatch.setenv("DSH_EVENTS_TOKEN", "dsh-token")
    monkeypatch.setenv("MEMORY_ENABLED", "false")
    get_settings.cache_clear()
    captured: dict[str, object] = {}
    _stream_stub(monkeypatch, captured)
    client = signed_client_factory("default")

    client.post("/api/assistant/stream", json={"text": "记住我喜欢早上处理难的任务"})
    event = captured["events"][0]
    assert "memoryEnabled" not in event and "userMemory" not in event
    assert client.get("/api/memory").json()["data"]["items"] == []


def test_user_memory_table_is_added_to_existing_database(app_env) -> None:
    init_db()
    with sqlite3.connect(app_env) as conn:
        conn.execute("DROP TABLE userMemory")
        conn.execute(
            "INSERT INTO assistantConversation(conversationId, userId, createdAt, updatedAt) "
            "VALUES ('keep-me', 'default', '2026-11-01T00:00:00+08:00', '2026-11-01T00:00:00+08:00')"
        )
        conn.commit()
    init_db()
    with sqlite3.connect(app_env) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(userMemory)")}
        kept = conn.execute(
            "SELECT COUNT(*) FROM assistantConversation WHERE conversationId = 'keep-me'"
        ).fetchone()[0]
    assert {"memoryId", "userId", "memType", "content", "source", "confidence", "lastUsedAt",
            "expiresAt", "deletedAt"} <= columns
    assert kept == 1
