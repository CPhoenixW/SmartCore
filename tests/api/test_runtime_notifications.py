from __future__ import annotations

from app.server.db.session import SessionLocal
from app.server.new_core.models import PushSubscription


def test_runtime_clock_returns_server_timezone_and_offset(signed_client_factory, monkeypatch) -> None:
    monkeypatch.setenv("DAILY_SUMMARY_TIMEZONE", "Asia/Shanghai")
    client = signed_client_factory("default")

    response = client.get("/api/runtime/clock?timezone=Asia%2FSingapore")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["timezone"] == "Asia/Singapore"
    assert data["serverNow"].endswith("+08:00")
    assert data["offsetMinutes"] == 480
    assert data["source"] == "server"


def test_push_subscription_is_owned_by_authenticated_user(signed_client_factory) -> None:
    endpoint = "https://push.example.test/subscription/one"
    payload = {"endpoint": endpoint, "keys": {"p256dh": "p" * 32, "auth": "a" * 16}}

    owner = signed_client_factory("default")
    created = owner.post("/api/notifications/push-subscription", json=payload)
    assert created.status_code == 200
    assert created.json()["data"]["subscribed"] is True

    db = SessionLocal()
    try:
        row = db.query(PushSubscription).filter_by(endpoint=endpoint).one()
        assert row.userId == "default"
    finally:
        db.close()

    registered = owner.post(
        "/api/auth/register",
        json={"loginName": "other-user", "password": "StrongPass123!"},
    )
    assert registered.status_code == 200
    other_id = registered.json()["data"]["userId"]
    other = signed_client_factory(other_id)
    deleted = other.request("DELETE", "/api/notifications/push-subscription", json=payload)
    assert deleted.status_code == 200
    assert deleted.json()["data"]["subscribed"] is False

    db = SessionLocal()
    try:
        assert db.query(PushSubscription).filter_by(endpoint=endpoint).one().userId == "default"
    finally:
        db.close()

