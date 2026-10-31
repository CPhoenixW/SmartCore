from __future__ import annotations

import httpx
from sqlalchemy import select

from app.server.config import get_settings
from app.server.db.session import SessionLocal
from app.server.new_core.models import AssistantConversation, AssistantMessage


class _StreamResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def raise_for_status(self):
        return None

    def iter_lines(self):
        yield 'data: {"type":"status","phase":"thinking","message":"正在查询…"}'
        yield ""
        yield 'data: {"type":"done","sessionId":"dsh-session","response":"这是历史回答"}'
        yield ""


def _enable_dsh(monkeypatch) -> None:
    monkeypatch.setenv("DSH_EVENTS_ENDPOINT", "http://dsh.local/api/smartcore/events")
    monkeypatch.setenv("DSH_EVENTS_TOKEN", "dsh-token")
    get_settings.cache_clear()


def test_assistant_stream_persists_conversation_and_searches(
    signed_client_factory, monkeypatch
) -> None:
    _enable_dsh(monkeypatch)
    captured: list[str] = []

    def stream(method: str, url: str, **_kwargs):
        captured.append(f"{method} {url}")
        return _StreamResponse()

    monkeypatch.setattr(httpx, "stream", stream)
    client = signed_client_factory("default")
    response = client.post(
        "/api/assistant/stream",
        json={
            "conversationId": "pwa-history-test",
            "clientMessageId": "client-history-1",
            "text": "查一下下周的课程",
            "timezone": "Asia/Shanghai",
        },
    )

    assert response.status_code == 200
    assert '"type": "done"' in response.text
    assert captured == ["POST http://dsh.local/api/smartcore/stream"]

    history = client.get("/api/assistant/conversations/pwa-history-test")
    assert history.status_code == 200
    assert [item["role"] for item in history.json()["data"]["messages"]] == ["user", "assistant"]

    search = client.get("/api/assistant/conversations", params={"q": "下周的课程"})
    assert search.status_code == 200
    assert search.json()["data"]["items"][0]["conversationId"] == "pwa-history-test"

    db = SessionLocal()
    try:
        assert db.scalar(select(AssistantConversation).where(AssistantConversation.conversationId == "pwa-history-test"))
        assert len(db.scalars(select(AssistantMessage).where(AssistantMessage.conversationId == "pwa-history-test")).all()) == 2
    finally:
        db.close()


def test_assistant_stream_client_message_is_idempotent(signed_client_factory, monkeypatch) -> None:
    _enable_dsh(monkeypatch)
    calls = 0

    def stream(_method: str, _url: str, **_kwargs):
        nonlocal calls
        calls += 1
        return _StreamResponse()

    monkeypatch.setattr(httpx, "stream", stream)
    client = signed_client_factory("default")
    payload = {
        "conversationId": "pwa-idempotent-test",
        "clientMessageId": "same-client-message",
        "text": "记录一个复习计划",
    }
    assert client.post("/api/assistant/stream", json=payload).status_code == 200
    replay = client.post("/api/assistant/stream", json=payload)
    assert replay.status_code == 200
    assert "正在加载历史回答" in replay.text
    assert calls == 1

    db = SessionLocal()
    try:
        rows = db.scalars(
            select(AssistantMessage).where(AssistantMessage.conversationId == "pwa-idempotent-test")
        ).all()
        assert len(rows) == 2
    finally:
        db.close()


def test_assistant_history_is_owner_scoped(signed_client_factory) -> None:
    owner = signed_client_factory("default")
    created = owner.post("/api/assistant/conversations", json={"title": "私密会话"})
    assert created.status_code == 200
    conversation_id = created.json()["data"]["conversationId"]

    registered = owner.post(
        "/api/auth/register",
        json={"loginName": "history-other", "password": "StrongPass123!"},
    )
    assert registered.status_code == 200
    other = signed_client_factory(registered.json()["data"]["userId"])
    assert other.get(f"/api/assistant/conversations/{conversation_id}").status_code == 404
    assert other.get("/api/assistant/conversations", params={"q": "私密"}).json()["data"]["items"] == []


def test_assistant_local_history_import_is_idempotent(signed_client_factory) -> None:
    client = signed_client_factory("default")
    payload = {
        "messages": [
            {"messageId": "old-user-1", "role": "user", "text": "旧问题", "createdAt": "2026-07-01T10:00:00+08:00"},
            {"messageId": "old-bot-1", "role": "assistant", "text": "旧回答", "createdAt": "2026-07-01T10:00:01+08:00"},
        ]
    }
    first = client.post("/api/assistant/conversations/pwa-import-test/import", json=payload)
    second = client.post("/api/assistant/conversations/pwa-import-test/import", json=payload)
    assert first.status_code == 200
    assert first.json()["data"]["imported"] == 2
    assert second.status_code == 200
    assert second.json()["data"]["imported"] == 0
    history = client.get("/api/assistant/conversations/pwa-import-test")
    assert [item["text"] for item in history.json()["data"]["messages"]] == ["旧问题", "旧回答"]


def test_assistant_stream_invalid_timezone_does_not_create_history(
    signed_client_factory, monkeypatch
) -> None:
    _enable_dsh(monkeypatch)
    client = signed_client_factory("default")
    response = client.post(
        "/api/assistant/stream",
        json={"conversationId": "pwa-invalid-timezone", "text": "你好", "timezone": "Not/AZone"},
    )
    assert response.status_code == 422
    db = SessionLocal()
    try:
        assert db.get(AssistantConversation, "pwa-invalid-timezone") is None
    finally:
        db.close()
