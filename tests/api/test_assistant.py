from __future__ import annotations

import json

import httpx

from app.server.config import get_settings


def test_assistant_message_forwards_authenticated_user_to_dsh(
    signed_client_factory, monkeypatch
) -> None:
    monkeypatch.setenv("DSH_EVENTS_ENDPOINT", "http://dsh.local/api/smartcore/events")
    monkeypatch.setenv("DSH_EVENTS_TOKEN", "dsh-token")
    get_settings.cache_clear()

    captured: dict[str, object] = {}

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"ok": True, "data": {"sessionId": "session-1", "response": "已记录"}}

    def post(url: str, **kwargs: object) -> Response:
        captured["url"] = url
        captured["kwargs"] = kwargs
        return Response()

    monkeypatch.setattr(httpx, "post", post)
    client = signed_client_factory("default")

    response = client.post(
        "/api/assistant/message",
        json={"text": "记录今天的复习", "sessionId": "pwa-1"},
    )

    assert response.status_code == 200
    assert response.json()["data"] == {"sessionId": "session-1", "response": "已记录"}
    assert captured["url"] == "http://dsh.local/api/smartcore/query"
    kwargs = captured["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["headers"] == {"Authorization": "Bearer dsh-token"}
    event = json.loads(json.dumps(kwargs["json"]))
    assert event["userId"] == "default"
    assert event["source"] == "web"
    assert event["conversationId"] == "pwa-1"
    assert event["text"] == "记录今天的复习"
    assert event["agentScope"]


def test_assistant_message_requires_login(client, monkeypatch) -> None:
    monkeypatch.setenv("DSH_EVENTS_ENDPOINT", "http://dsh.local/api/smartcore/events")
    monkeypatch.setenv("DSH_EVENTS_TOKEN", "dsh-token")
    get_settings.cache_clear()

    response = client.post("/api/assistant/message", json={"text": "你好"})

    assert response.status_code == 401
