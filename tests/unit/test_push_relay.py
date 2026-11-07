from __future__ import annotations

import base64

import pytest

from app.server.config import Settings
from app.server.new_core.push import (
    FcmRelaySession,
    push_requests_session,
    send_web_push,
    uses_push_relay,
)

pytestmark = pytest.mark.unit


def test_only_chrome_push_endpoints_use_the_relay() -> None:
    assert uses_push_relay("https://fcm.googleapis.com/fcm/send/device")
    assert uses_push_relay("https://fcm.googleapis.com/wp/device")
    assert not uses_push_relay("https://updates.push.services.mozilla.com/wpush/v2/device")
    assert not uses_push_relay("http://fcm.googleapis.com/fcm/send/device")


def test_relay_session_posts_the_encrypted_request(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    class Response:
        status_code = 201
        text = ""
        reason = "Created"

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("app.server.new_core.push.requests.post", fake_post)
    session = FcmRelaySession("https://smartcore.example/push-relay", "secret")
    session.post(
        "https://fcm.googleapis.com/fcm/send/device",
        data=b"\x01\x02",
        headers={"Authorization": "vapid t=1", "TTL": 60},
        timeout=5,
    )
    assert captured["url"] == "https://smartcore.example/push-relay"
    assert captured["headers"] == {"Authorization": "Bearer secret"}
    assert captured["timeout"] == 5
    assert captured["json"]["url"] == "https://fcm.googleapis.com/fcm/send/device"
    assert captured["json"]["headers"]["TTL"] == "60"
    assert base64.b64decode(captured["json"]["body"]) == b"\x01\x02"


def test_send_uses_the_relay_only_when_it_is_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict = {}

    class Response:
        status_code = 201

    def fake_webpush(**kwargs):
        seen["session"] = kwargs.get("requests_session")
        return Response()

    class Row:
        endpoint = "https://fcm.googleapis.com/fcm/send/device"
        p256dh = "key"
        auth = "auth"

    class Result:
        def all(self):
            return [Row()]

    class Database:
        def scalars(self, _query):
            return Result()

    monkeypatch.setattr("pywebpush.webpush", fake_webpush)
    settings = Settings(
        pwa_push_enabled=True,
        pwa_push_vapid_public_key="public",
        pwa_push_vapid_private_key="private",
        pwa_push_vapid_subject="https://smartcore.example",
        pwa_push_relay_url="https://smartcore.example/push-relay",
        pwa_push_relay_token="secret",
    )
    ok, reason = send_web_push(
        Database(),
        user_id="default",
        title="测试",
        content="内容",
        settings=settings,
    )
    assert (ok, reason) == (True, None)
    assert isinstance(seen["session"], FcmRelaySession)
    assert push_requests_session(Settings()) is None
