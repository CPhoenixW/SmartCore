from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

from app.server.computer.insights import dispatch_smart_plan_reminders
from app.server.computer.service import cleanup_activity
from app.server.config import Settings
from app.server.db.session import SessionLocal
from app.server.new_core.scheduler import runReminderTick
from app.server.scheduler.computer_analysis import (
    dispatch_daily_work_logs,
    dispatch_hourly_analyses,
)
from app.server.scheduler.daily_summary import dispatch_daily_summaries
from app.server.screen.manager import screenManager
from app.server.weather.service import deliver_tomorrow_weather, refresh_weather


def build_scheduler_service(
    settings: Settings,
    *,
    session_factory: Callable[[], Session] | None = None,
    scheduler: BackgroundScheduler | None = None,
) -> SchedulerService | None:
    if (
        not settings.scheduler_enabled
        and not settings.daily_summary_enabled
        and not settings.weather_enabled
        and not settings.computer_analysis_enabled
        and settings.computer_activity_retention_days < 1
    ):
        return None
    if session_factory is None:
        session_factory = SessionLocal
    return SchedulerService(
        settings=settings,
        session_factory=session_factory,
        scheduler=scheduler,
    )


class SchedulerService:
    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: Callable[[], Session],
        scheduler: BackgroundScheduler | None = None,
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._scheduler = scheduler or BackgroundScheduler(timezone=settings.daily_summary_timezone)

    def _tick(self) -> None:
        from app.server.new_core.models import nowIso

        db = self._session_factory()
        try:
            runReminderTick(db, now=nowIso(), screenOnline=screenManager.online())
        finally:
            db.close()

    def _daily_summary_tick(self) -> None:
        db = self._session_factory()
        try:
            dispatch_daily_summaries(
                db,
                settings=self._settings,
                now=datetime.now(ZoneInfo(self._settings.daily_summary_timezone)),
            )
        finally:
            db.close()

    def _weather_refresh_tick(self) -> None:
        db = self._session_factory()
        try:
            refresh_weather(db, settings=self._settings)
        finally:
            db.close()

    def _weather_daily_tick(self) -> None:
        db = self._session_factory()
        try:
            deliver_tomorrow_weather(
                db,
                settings=self._settings,
                now=datetime.now(ZoneInfo(self._settings.weather_timezone)),
                refresh=False,
            )
        finally:
            db.close()

    def _computer_cleanup_tick(self) -> None:
        db = self._session_factory()
        try:
            cleanup_activity(
                db,
                retention_days=self._settings.computer_activity_retention_days,
            )
        finally:
            db.close()

    def _computer_hourly_analysis_tick(self) -> None:
        db = self._session_factory()
        try:
            dispatch_hourly_analyses(
                db,
                settings=self._settings,
                now=datetime.now(ZoneInfo(self._settings.computer_analysis_timezone)),
            )
        finally:
            db.close()

    def _computer_daily_log_tick(self) -> None:
        db = self._session_factory()
        try:
            dispatch_daily_work_logs(
                db,
                settings=self._settings,
                now=datetime.now(ZoneInfo(self._settings.computer_analysis_timezone)),
            )
        finally:
            db.close()

    def _computer_smart_reminder_tick(self) -> None:
        db = self._session_factory()
        try:
            dispatch_smart_plan_reminders(
                db,
                now=datetime.now(ZoneInfo(self._settings.computer_analysis_timezone)),
                screen_online=screenManager.online,
            )
        finally:
            db.close()

    def start(self) -> None:
        if self._settings.scheduler_enabled:
            self._scheduler.add_job(
                self._tick,
                trigger="interval",
                seconds=self._settings.scheduler_interval_seconds,
                id="smartcore-reminder-tick",
                replace_existing=True,
            )
        if self._settings.daily_summary_enabled:
            if not 0 <= self._settings.daily_summary_hour <= 23:
                raise ValueError("DAILY_SUMMARY_HOUR must be between 0 and 23")
            if not 0 <= self._settings.daily_summary_minute <= 59:
                raise ValueError("DAILY_SUMMARY_MINUTE must be between 0 and 59")
            ZoneInfo(self._settings.daily_summary_timezone)
            self._scheduler.add_job(
                self._daily_summary_tick,
                trigger="cron",
                hour=self._settings.daily_summary_hour,
                minute=self._settings.daily_summary_minute,
                timezone=self._settings.daily_summary_timezone,
                id="smartcore-daily-summary",
                replace_existing=True,
                coalesce=True,
                max_instances=1,
                misfire_grace_time=300,
            )
        if self._settings.weather_enabled:
            if not 5 <= self._settings.weather_refresh_minutes <= 1440:
                raise ValueError("WEATHER_REFRESH_MINUTES must be between 5 and 1440")
            if not 0 <= self._settings.weather_daily_hour <= 23:
                raise ValueError("WEATHER_DAILY_HOUR must be between 0 and 23")
            if not 0 <= self._settings.weather_daily_minute <= 59:
                raise ValueError("WEATHER_DAILY_MINUTE must be between 0 and 59")
            weather_timezone = ZoneInfo(self._settings.weather_timezone)
            self._scheduler.add_job(
                self._weather_refresh_tick,
                trigger="interval",
                minutes=self._settings.weather_refresh_minutes,
                next_run_time=datetime.now(weather_timezone),
                id="smartcore-weather-refresh",
                replace_existing=True,
                coalesce=True,
                max_instances=1,
            )
            self._scheduler.add_job(
                self._weather_daily_tick,
                trigger="cron",
                hour=self._settings.weather_daily_hour,
                minute=self._settings.weather_daily_minute,
                timezone=self._settings.weather_timezone,
                id="smartcore-weather-daily",
                replace_existing=True,
                coalesce=True,
                max_instances=1,
                misfire_grace_time=300,
            )
        if self._settings.computer_activity_retention_days > 0:
            self._scheduler.add_job(
                self._computer_cleanup_tick,
                trigger="cron",
                hour=3,
                minute=20,
                timezone=self._settings.daily_summary_timezone,
                id="smartcore-computer-activity-cleanup",
                replace_existing=True,
                coalesce=True,
                max_instances=1,
                misfire_grace_time=3600,
            )
        if self._settings.computer_analysis_enabled:
            if not 0 <= self._settings.computer_analysis_minute <= 59:
                raise ValueError("COMPUTER_ANALYSIS_MINUTE must be between 0 and 59")
            ZoneInfo(self._settings.computer_analysis_timezone)
            self._scheduler.add_job(
                self._computer_hourly_analysis_tick,
                trigger="cron",
                minute=self._settings.computer_analysis_minute,
                timezone=self._settings.computer_analysis_timezone,
                id="smartcore-computer-hourly-analysis",
                replace_existing=True,
                coalesce=True,
                max_instances=1,
                misfire_grace_time=900,
            )
            self._scheduler.add_job(
                self._computer_daily_log_tick,
                trigger="cron",
                hour=23,
                minute=59,
                timezone=self._settings.computer_analysis_timezone,
                id="smartcore-computer-daily-work-log",
                replace_existing=True,
                coalesce=True,
                max_instances=1,
                misfire_grace_time=900,
            )
            self._scheduler.add_job(
                self._computer_smart_reminder_tick,
                trigger="interval",
                seconds=60,
                id="smartcore-computer-smart-reminders",
                replace_existing=True,
                coalesce=True,
                max_instances=1,
            )
        self._scheduler.start()

    def shutdown(self) -> None:
        self._scheduler.shutdown(wait=False)
