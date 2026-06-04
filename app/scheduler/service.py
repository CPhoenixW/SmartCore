from __future__ import annotations

from collections.abc import Callable
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

from app.config import Settings
from app.feishu.client import FeishuClient, FeishuNotificationSender
from app.scheduler.reminder_engine import NotificationSender, SchedulerConfig
from app.scheduler.runner import SchedulerRunner


def _scheduler_push_configured(settings: Settings) -> bool:
    if not settings.scheduler_enabled:
        return False
    if not settings.feishu_default_chat_id.strip():
        return False
    if not settings.feishu_app_id.strip() or not settings.feishu_app_secret.strip():
        return False
    return True


def build_scheduler_runner(
    settings: Settings,
    *,
    session_factory: Callable[[], Session],
    sender: NotificationSender | None = None,
) -> SchedulerRunner | None:
    if not _scheduler_push_configured(settings):
        return None

    if sender is None:
        client = FeishuClient(settings.feishu_app_id, settings.feishu_app_secret)
        sender = FeishuNotificationSender(client, settings.feishu_default_chat_id)

    config = SchedulerConfig(semester_start=settings.semester_start)
    return SchedulerRunner(session_factory, sender, config)


def build_scheduler_service(
    settings: Settings,
    *,
    session_factory: Callable[[], Session] | None = None,
    sender: NotificationSender | None = None,
    scheduler: Any | None = None,
) -> SchedulerService | None:
    if session_factory is None:
        from app.db.session import SessionLocal

        session_factory = SessionLocal

    runner = build_scheduler_runner(
        settings,
        session_factory=session_factory,
        sender=sender,
    )
    if runner is None:
        return None

    return SchedulerService(
        runner=runner,
        interval_seconds=settings.scheduler_interval_seconds,
        scheduler=scheduler,
    )


class SchedulerService:
    """APScheduler-backed wrapper that ticks the reminder runner on an interval."""

    def __init__(
        self,
        *,
        runner: SchedulerRunner,
        interval_seconds: int,
        scheduler: Any | None = None,
    ) -> None:
        self._runner = runner
        self._interval_seconds = interval_seconds
        self._scheduler = scheduler or BackgroundScheduler()

    def start(self) -> None:
        self._scheduler.add_job(
            self._runner.tick,
            trigger="interval",
            seconds=self._interval_seconds,
            id="smartcore-reminder-tick",
            replace_existing=True,
        )
        self._scheduler.start()

    def shutdown(self) -> None:
        self._scheduler.shutdown(wait=False)
