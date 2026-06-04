from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.db.models import Notification, NotificationDelivery, NotificationStatus
from app.notifications.channels import NotificationChannel


class NotificationDispatcher:
    def __init__(self, channels: dict[str, NotificationChannel]) -> None:
        self._channels = channels

    def dispatch_due(self, db: Session, *, now: datetime) -> int:
        due = (
            db.query(Notification)
            .filter(
                Notification.status == NotificationStatus.PENDING.value,
                Notification.scheduled_at <= now,
            )
            .order_by(Notification.scheduled_at)
            .all()
        )
        sent = 0
        for notification in due:
            if self._dispatch_one(db, notification):
                sent += 1
        return sent

    def _dispatch_one(self, db: Session, notification: Notification) -> bool:
        channel = self._channels.get(notification.channel)
        if channel is None:
            delivery = NotificationDelivery(
                notification_id=notification.id,
                channel=notification.channel,
                target=notification.target,
                status="failed",
                error_message=f"unknown channel: {notification.channel}",
            )
            db.add(delivery)
            notification.retry_count += 1
            db.commit()
            return False

        result = channel.send(
            target=notification.target,
            title=notification.title,
            content=notification.content,
        )
        delivery = NotificationDelivery(
            notification_id=notification.id,
            channel=notification.channel,
            target=notification.target,
            status="sent" if result.success else "failed",
            external_message_id=result.external_message_id,
            error_message=result.error_message,
        )
        db.add(delivery)
        if result.success:
            notification.status = NotificationStatus.SENT.value
            notification.sent_at = datetime.now(tz=notification.scheduled_at.tzinfo)
            db.commit()
            return True

        notification.retry_count += 1
        db.commit()
        return False
