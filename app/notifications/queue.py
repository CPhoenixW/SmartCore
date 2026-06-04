from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.db.models import Notification, NotificationStatus


def enqueue_notification(
    db: Session,
    *,
    notification_type: str,
    channel: str,
    target: str,
    title: str,
    content: str,
    scheduled_at: datetime,
) -> Notification:
    notification = Notification(
        notification_type=notification_type,
        channel=channel,
        target=target,
        title=title,
        content=content,
        scheduled_at=scheduled_at,
        status=NotificationStatus.PENDING.value,
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification
