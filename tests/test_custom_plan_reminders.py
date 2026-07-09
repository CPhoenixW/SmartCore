from __future__ import annotations

from datetime import datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.session import Base
from app.new_core.custom_reminders import (
    localized_reminder_message,
    replace_extra_reminders,
    sync_extra_reminders,
)
from app.new_core.event_relations import create_plan_event, get_event, update_event
from app.new_core.models import AppUser, EvtBase, RemindEvt


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return Session(engine)


def test_plan_creation_keeps_two_defaults_and_adds_extra_reminders() -> None:
    db = _session()
    try:
        plan = create_plan_event(
            db,
            title="Review",
            stTime="2026-09-15T08:00:00+08:00",
            durationMin=60,
            commit=False,
        )
        replace_extra_reminders(
            db,
            plan["evtId"],
            [
                {"anchor": "start", "offsetMin": 30},
                {"anchor": "end", "offsetMin": 0},
                {"anchor": "start", "offsetMin": 10},
            ],
            commit=False,
        )
        db.commit()

        created = get_event(db, plan["evtId"])
        assert len(created["reminders"]) == 4
        assert {item["remindKind"] for item in created["reminders"]} == {
            "plan_start_10m",
            "plan_end_10m",
            "custom_start_30m",
            "custom_end_0m",
        }
    finally:
        db.close()


def test_custom_reminders_follow_plan_time_changes() -> None:
    db = _session()
    try:
        plan = create_plan_event(
            db,
            title="Review",
            stTime="2026-09-15T08:00:00+08:00",
            durationMin=60,
            commit=False,
        )
        replace_extra_reminders(
            db,
            plan["evtId"],
            [{"anchor": "start", "offsetMin": 30}],
            commit=False,
        )
        db.commit()

        update_event(
            db,
            plan["evtId"],
            stTime="2026-09-15T10:00:00+08:00",
        )
        sync_extra_reminders(db, plan["evtId"])

        reminder = db.scalar(
            select(RemindEvt).where(RemindEvt.remindKind == "custom_start_30m")
        )
        assert reminder is not None
        assert datetime.fromisoformat(reminder.triggerTime).hour == 9
        assert datetime.fromisoformat(reminder.triggerTime).minute == 30
    finally:
        db.close()


def test_reminder_delivery_copy_uses_current_user_language() -> None:
    db = _session()
    try:
        plan = create_plan_event(
            db,
            title="Review",
            stTime="2026-09-15T08:00:00+08:00",
            durationMin=60,
            commit=False,
        )
        replace_extra_reminders(
            db,
            plan["evtId"],
            [{"anchor": "start", "offsetMin": 30}],
            commit=False,
        )
        user = db.get(AppUser, "default")
        assert user is not None
        user.language = "en"
        db.commit()

        reminder = db.scalar(
            select(RemindEvt).where(RemindEvt.remindKind == "custom_start_30m")
        )
        plan_base = db.get(EvtBase, plan["evtId"])
        assert reminder is not None and plan_base is not None
        title, content = localized_reminder_message(db, reminder, plan_base)
        assert "30 min before" in title
        assert "in 30 minutes" in content
    finally:
        db.close()
