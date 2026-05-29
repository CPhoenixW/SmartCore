from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from sqlalchemy.orm import Session

from app.scheduler.reminder_engine import NotificationSender, ReminderEngine, SchedulerConfig


class SchedulerRunner:
    """Coordinates reminder generation and dispatch for a scheduler tick."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        sender: NotificationSender,
        config: SchedulerConfig | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.sender = sender
        self.engine = ReminderEngine(config)

    def tick(self, *, now: datetime | None = None) -> tuple[int, int]:
        db = self.session_factory()
        try:
            created = self.engine.generate_reminders(db, now=now)
            sent = self.engine.dispatch_due_reminders(db, self.sender, now=now)
            return created, sent
        finally:
            db.close()

    def generate_only(self, *, now: datetime | None = None) -> int:
        db = self.session_factory()
        try:
            return self.engine.generate_reminders(db, now=now)
        finally:
            db.close()

    def dispatch_only(self, *, now: datetime | None = None) -> int:
        db = self.session_factory()
        try:
            return self.engine.dispatch_due_reminders(db, self.sender, now=now)
        finally:
            db.close()
