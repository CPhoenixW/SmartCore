from __future__ import annotations

from datetime import datetime

from app.db.models import Notification, NotificationDelivery, NotificationStatus
from app.notifications.channels import NotificationChannel, NotificationSendResult
from app.notifications.dispatcher import NotificationDispatcher
from app.notifications.queue import enqueue_notification
from app.secretary.rules import DEFAULT_TZ


class RecordingChannel(NotificationChannel):
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.sent: list[str] = []

    def send(self, *, target: str, title: str, content: str) -> NotificationSendResult:
        if self.fail:
            return NotificationSendResult(success=False, error_message="send failed")
        self.sent.append(f"{target}:{title}:{content}")
        return NotificationSendResult(success=True, external_message_id="msg-1")


def test_enqueue_notification_persists_pending_notification(db_session) -> None:
    scheduled_at = datetime(2026, 6, 10, 7, 0, tzinfo=DEFAULT_TZ)

    notification = enqueue_notification(
        db_session,
        notification_type="daily_digest",
        channel="feishu",
        target="oc_default",
        title="今日晨报",
        content="今天有 2 节课。",
        scheduled_at=scheduled_at,
    )

    assert notification.id is not None
    assert notification.status == NotificationStatus.PENDING.value
    assert notification.scheduled_at == scheduled_at


def test_dispatcher_sends_due_notification_and_records_delivery(db_session) -> None:
    scheduled_at = datetime(2026, 6, 10, 7, 0, tzinfo=DEFAULT_TZ)
    enqueue_notification(
        db_session,
        notification_type="daily_digest",
        channel="feishu",
        target="oc_default",
        title="今日晨报",
        content="今天有 2 节课。",
        scheduled_at=scheduled_at,
    )
    channel = RecordingChannel()
    dispatcher = NotificationDispatcher({"feishu": channel})

    sent = dispatcher.dispatch_due(
        db_session,
        now=datetime(2026, 6, 10, 7, 5, tzinfo=DEFAULT_TZ),
    )

    notification = db_session.query(Notification).one()
    delivery = db_session.query(NotificationDelivery).one()
    assert sent == 1
    assert channel.sent == ["oc_default:今日晨报:今天有 2 节课。"]
    assert notification.status == NotificationStatus.SENT.value
    assert delivery.status == "sent"
    assert delivery.external_message_id == "msg-1"


def test_dispatcher_records_failed_delivery_without_losing_notification(db_session) -> None:
    scheduled_at = datetime(2026, 6, 10, 7, 0, tzinfo=DEFAULT_TZ)
    enqueue_notification(
        db_session,
        notification_type="daily_digest",
        channel="feishu",
        target="oc_default",
        title="今日晨报",
        content="今天有 2 节课。",
        scheduled_at=scheduled_at,
    )
    dispatcher = NotificationDispatcher({"feishu": RecordingChannel(fail=True)})

    sent = dispatcher.dispatch_due(
        db_session,
        now=datetime(2026, 6, 10, 7, 5, tzinfo=DEFAULT_TZ),
    )

    notification = db_session.query(Notification).one()
    delivery = db_session.query(NotificationDelivery).one()
    assert sent == 0
    assert notification.status == NotificationStatus.PENDING.value
    assert notification.retry_count == 1
    assert delivery.status == "failed"
    assert delivery.error_message == "send failed"
