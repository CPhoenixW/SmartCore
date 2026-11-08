from __future__ import annotations

import pytest

from app.server.api.notification_routes import _delivery_detail, _delivery_state
from app.server.config import Settings
from app.server.new_core import crud
from app.server.new_core.models import NotifyLog
from app.server.new_core.push import send_web_push

pytestmark = pytest.mark.unit


def test_failed_notify_log_has_no_sent_at(db_session) -> None:
    failed = crud.writeNotifyLog(
        db_session,
        dedupKey=None,
        channel="browser",
        title="测试",
        content="推送失败",
        stat="failed",
        failReason="provider timeout",
    )
    assert failed["sentAt"] is None
    row = db_session.query(NotifyLog).one()
    assert row.sentAt is None


def test_browser_notify_log_exposes_provider_acceptance_without_claiming_display(db_session) -> None:
    accepted = crud.writeNotifyLog(
        db_session,
        dedupKey="notify:accepted",
        channel="browser",
        title="测试",
        content="推送服务已接收",
        stat="sent",
    )
    row = db_session.query(NotifyLog).one()
    assert accepted["sentAt"] is not None
    assert _delivery_state(row) == "accepted"
    assert _delivery_detail(row) == "push_provider_accepted"


def test_web_push_non_2xx_response_is_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        status_code = 503

    class Row:
        endpoint = "https://fcm.googleapis.com/fcm/send/device"
        p256dh = "p" * 32
        auth = "a" * 16

    class Result:
        def all(self):
            return [Row()]

    class Database:
        def scalars(self, _query):
            return Result()

    def fake_webpush(**_kwargs):
        return Response()

    monkeypatch.setattr("pywebpush.webpush", fake_webpush)
    settings = Settings(
        pwa_push_enabled=True,
        pwa_push_vapid_public_key="public",
        pwa_push_vapid_private_key="private",
        pwa_push_vapid_subject="https://smartcore.example",
    )
    ok, reason = send_web_push(
        Database(),
        user_id="default",
        title="测试",
        content="内容",
        settings=settings,
    )
    assert ok is False
    assert reason == "all browser push deliveries failed"
