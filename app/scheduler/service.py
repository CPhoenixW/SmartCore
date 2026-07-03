from __future__ import annotations

from collections.abc import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.session import SessionLocal
from app.new_core.scheduler import runReminderTick
from app.screen.manager import screenManager


def build_scheduler_service(
    settings: Settings,
    *,
    session_factory: Callable[[], Session] | None = None,
    scheduler: BackgroundScheduler | None = None,
) -> SchedulerService | None:
    if not settings.scheduler_enabled:
        return None
    if session_factory is None:
        session_factory = SessionLocal
    return SchedulerService(
        session_factory=session_factory,
        interval_seconds=settings.scheduler_interval_seconds,
        scheduler=scheduler,
    )


class SchedulerService:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        interval_seconds: int,
        scheduler: BackgroundScheduler | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._interval_seconds = interval_seconds
        self._scheduler = scheduler or BackgroundScheduler()

    def _tick(self) -> None:
        from app.new_core.models import nowIso

        db = self._session_factory()
        try:
            runReminderTick(db, now=nowIso(), screenOnline=screenManager.online)
        finally:
            db.close()

    def start(self) -> None:
        self._scheduler.add_job(
            self._tick,
            trigger="interval",
            seconds=self._interval_seconds,
            id="smartcore-reminder-tick",
            replace_existing=True,
        )
        self._scheduler.start()

    def shutdown(self) -> None:
        self._scheduler.shutdown(wait=False)
