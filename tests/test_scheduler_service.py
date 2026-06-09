from __future__ import annotations

from datetime import date, datetime

from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.db import crud
from app.db.models import WeekRule
from app.scheduler.reminder_engine import NotificationSendError
from app.secretary.rules import DEFAULT_TZ

SEMESTER_START = date(2026, 2, 23)


class RecordingSender:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.messages: list[str] = []

    def send(self, *, card=None, text: str = "") -> None:
        if self.fail:
            raise NotificationSendError("send failed")
        self.messages.append(text)


class DummyRunner:
    def __init__(self) -> None:
        self.ticks = 0

    def tick(self) -> int:
        self.ticks += 1
        return 0


class FakeScheduler:
    def __init__(self) -> None:
        self.jobs: list[dict] = []
        self.started = False
        self.shutdown_wait: bool | None = None

    def add_job(self, func, trigger: str, **kwargs) -> None:
        self.jobs.append({"func": func, "trigger": trigger, **kwargs})

    def start(self) -> None:
        self.started = True

    def shutdown(self, *, wait: bool = True) -> None:
        self.shutdown_wait = wait


def test_scheduler_service_registers_interval_tick_job() -> None:
    from app.scheduler.service import SchedulerService

    runner = DummyRunner()
    scheduler = FakeScheduler()
    service = SchedulerService(
        runner=runner,
        interval_seconds=30,
        scheduler=scheduler,
    )

    service.start()

    assert scheduler.started is True
    assert len(scheduler.jobs) == 1
    job = scheduler.jobs[0]
    assert job["trigger"] == "interval"
    assert job["seconds"] == 30
    assert job["id"] == "smartcore-reminder-tick"
    assert job["replace_existing"] is True

    job["func"]()
    assert runner.ticks == 1

    service.shutdown()
    assert scheduler.shutdown_wait is False


def test_build_scheduler_runner_returns_none_when_disabled(db_session) -> None:
    from app.scheduler.service import build_scheduler_runner

    settings = Settings(
        scheduler_enabled=False,
        feishu_app_id="cli_test",
        feishu_app_secret="secret",
        feishu_default_chat_id="oc_default",
        semester_start=SEMESTER_START,
    )

    runner = build_scheduler_runner(
        settings,
        session_factory=lambda: db_session,
        sender=RecordingSender(),
    )

    assert runner is None


def test_build_scheduler_runner_requires_push_target(db_session) -> None:
    from app.scheduler.service import build_scheduler_runner

    settings = Settings(
        scheduler_enabled=True,
        feishu_app_id="cli_test",
        feishu_app_secret="secret",
        feishu_default_chat_id="",
        semester_start=SEMESTER_START,
    )

    runner = build_scheduler_runner(
        settings,
        session_factory=lambda: db_session,
        sender=RecordingSender(),
    )

    assert runner is None


def test_enabled_scheduler_runner_generates_and_sends_due_reminders(db_session) -> None:
    from app.scheduler.service import build_scheduler_runner

    course = crud.create_course(
        db_session,
        name="Algorithms",
        default_location="Room A101",
    )
    crud.create_course_session(
        db_session,
        course_id=course.id,
        weekday=1,
        start_time="08:00",
        end_time="09:40",
        week_rule=WeekRule.EVERY,
    )
    sender = RecordingSender()
    settings = Settings(
        scheduler_enabled=True,
        scheduler_interval_seconds=30,
        feishu_app_id="cli_test",
        feishu_app_secret="secret",
        feishu_default_chat_id="oc_default",
        semester_start=SEMESTER_START,
    )

    runner = build_scheduler_runner(
        settings,
        session_factory=lambda: db_session,
        sender=sender,
    )

    assert runner is not None
    sent = runner.tick(now=datetime(2026, 3, 2, 21, 0, tzinfo=DEFAULT_TZ))
    assert sent > 0
    assert sender.messages


def test_app_lifespan_starts_and_stops_scheduler_service(monkeypatch) -> None:
    from app import main as main_module

    class FakeSchedulerService:
        def __init__(self) -> None:
            self.started = False
            self.stopped = False

        def start(self) -> None:
            self.started = True

        def shutdown(self) -> None:
            self.stopped = True

    fake_service = FakeSchedulerService()

    def fake_build_scheduler_service(settings):
        assert settings.scheduler_enabled is True
        return fake_service

    monkeypatch.setenv("SCHEDULER_ENABLED", "true")
    monkeypatch.setenv("FEISHU_APP_ID", "cli_test")
    monkeypatch.setenv("FEISHU_APP_SECRET", "secret")
    monkeypatch.setenv("FEISHU_DEFAULT_CHAT_ID", "oc_default")
    get_settings.cache_clear()
    monkeypatch.setattr(
        main_module,
        "build_scheduler_service",
        fake_build_scheduler_service,
        raising=False,
    )

    with TestClient(main_module.create_app()) as client:
        assert client.get("/healthz").status_code == 200
        assert fake_service.started is True

    assert fake_service.stopped is True
    get_settings.cache_clear()
