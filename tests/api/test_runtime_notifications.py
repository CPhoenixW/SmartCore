from __future__ import annotations

from app.server.db.session import SessionLocal
from app.server.new_core import crud
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


def test_notification_reads_are_private_etag_cacheable(signed_client_factory) -> None:
    client = signed_client_factory("default")

    first = client.get("/api/notifications")

    assert first.status_code == 200
    assert first.headers["cache-control"] == "private, max-age=15, stale-while-revalidate=30"
    etag = first.headers["etag"]
    assert etag

    second = client.get("/api/notifications", headers={"If-None-Match": etag})

    assert second.status_code == 304
    assert second.content == b""
    assert second.headers["etag"] == etag


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



def test_notification_api_distinguishes_provider_acceptance_from_device_display(signed_client_factory) -> None:
    db = SessionLocal()
    try:
        crud.writeNotifyLog(
            db,
            dedupKey="api:accepted",
            channel="browser",
            title="推送服务接收",
            content="手机是否显示仍未确认",
            stat="sent",
        )
        crud.writeNotifyLog(
            db,
            dedupKey="api:failed",
            channel="browser",
            title="推送失败",
            content="provider timeout",
            stat="failed",
            failReason="provider timeout",
        )
    finally:
        db.close()

    response = signed_client_factory("default").get("/api/notifications?limit=10")

    assert response.status_code == 200
    rows = {row["stat"]: row for row in response.json()["data"]}
    assert rows["sent"]["deliveryState"] == "accepted"
    assert rows["sent"]["deliveryDetail"] == "push_provider_accepted"
    assert rows["failed"]["deliveryState"] == "failed"
    assert rows["failed"]["sentAt"] is None
    assert rows["failed"]["deliveryDetail"] == "provider timeout"
