from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.server.db.session import Base
from app.server.new_core import crud, scheduler
from app.server.new_core.event_relations import create_plan_event
from app.server.new_core.models import AppUser, EvtBase, PlanEvt, RemindEvt  # noqa: F401
from app.server.new_core.preferences import (
    UserPreference,  # noqa: F401
    get_user_preferences,
    update_user_preferences,
)


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return Session(engine)


def test_reminder_channel_defaults_to_screen_and_can_use_feishu() -> None:
    db = _session()
    try:
        assert get_user_preferences(db)["reminderChannel"] == "screen"
        updated = update_user_preferences(db, reminder_channel="feishu")
        assert updated["reminderChannel"] == "feishu"
        assert get_user_preferences(db)["reminderChannel"] == "feishu"
    finally:
        db.close()


def test_plan_owns_start_and_end_minus_ten_reminders(monkeypatch) -> None:
    db = _session()
    try:
        event = create_plan_event(
            db,
            title="Long plan",
            stTime="2026-07-08T10:00:00+08:00",
            durationMin=30,
        )
        assert [item["remindKind"] for item in event["reminders"]] == [
            "plan_start_10m",
            "plan_end_10m",
        ]
        assert [item["triggerTime"] for item in event["reminders"]] == [
            "2026-07-08T09:50:00+08:00",
            "2026-07-08T10:20:00+08:00",
        ]

        calls: list[dict[str, str]] = []
        monkeypatch.setattr(
            scheduler,
            "routeNotify",
            lambda *args, **kwargs: calls.append(kwargs) or {"channel": "screen", "stat": "sent"},
        )
        monkeypatch.setattr(crud, "notifyDedupExists", lambda db, key: False)

        scheduler.runReminderTick(
            db,
            now="2026-07-08T09:50:30+08:00",
            screenOnline=True,
        )
        assert len(calls) == 1
        assert calls[0]["phase"] == "start"
        assert calls[0]["evtId"] == event["evtId"]
        assert "开始前 10 分钟" in calls[0]["title"]

        calls.clear()
        scheduler.runReminderTick(
            db,
            now="2026-07-08T10:20:30+08:00",
            screenOnline=True,
        )
        assert len(calls) == 1
        assert calls[0]["phase"] == "notice"
        assert "结束前 10 分钟" in calls[0]["title"]
    finally:
        db.close()
