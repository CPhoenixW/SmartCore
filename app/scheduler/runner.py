from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from sqlalchemy.orm import Session

from app.scheduler.reminder_engine import NotificationSender, ReminderEngine, SchedulerConfig


class SchedulerRunner:
    """Scan schedule data and dispatch due notifications on each tick."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        sender: NotificationSender,
        config: SchedulerConfig | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.sender = sender
        self.engine = ReminderEngine(config)

    def tick(self, *, now: datetime | None = None) -> int:
        db = self.session_factory()
        try:
            return self.engine.scan_and_notify(db, self.sender, now=now)
        finally:
            db.close()
