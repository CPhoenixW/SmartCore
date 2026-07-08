from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.session import Base
from app.new_core import crud, scheduler
from app.new_core.models import AppUser, EvtBase, PlanEvt  # noqa: F401
from app.new_core.preferences import (
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


def test_plan_start_and_end_use_different_reminder_phases(monkeypatch) -> None:
    db = _session()
    try:
        event = crud.createPlanEvt(
            db,
            title="Long plan",
            stTime="2026-07-08T10:00:00+08:00",
            durationMin=30,
        )
        calls: list[dict[str, str]] = []

        monkeypatch.setattr(
            scheduler,
            "routeNotify",
            lambda *args, **kwargs: calls.append(kwargs) or {"channel": "screen", "stat": "sent"},
        )
        monkeypatch.setattr(crud, "notifyDedupExists", lambda db, key: False)

        scheduler.runReminderTick(
            db,
            now="2026-07-08T10:05:00+08:00",
            screenOnline=True,
        )
        assert [call["phase"] for call in calls] == ["start"]

        calls.clear()
        monkeypatch.setattr(
            crud,
            "notifyDedupExists",
            lambda db, key: key.startswith(f"planStart:{event['evtId']}"),
        )
        scheduler.runReminderTick(
            db,
            now="2026-07-08T10:31:00+08:00",
            screenOnline=True,
        )
        assert [call["phase"] for call in calls] == ["end"]
    finally:
        db.close()
