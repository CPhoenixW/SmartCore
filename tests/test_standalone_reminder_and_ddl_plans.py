from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.session import Base
from app.new_core.ddl_service import create_ddl_event, replace_ddl_plans
from app.new_core.event_relations import create_plan_event, get_event
from app.new_core.models import RemindEvt
from app.new_core.reminder_service import (
    create_reminder_event,
    list_reminder_events,
    update_reminder_event,
)


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return Session(engine)


def test_plan_keeps_two_hidden_automatic_reminders() -> None:
    db = _session()
    try:
        plan = create_plan_event(
            db,
            title="Review",
            stTime="2026-09-15T08:00:00+08:00",
            durationMin=60,
        )
        reminder_rows = db.scalars(
            select(RemindEvt).where(RemindEvt.planEvtId == plan["evtId"])
        ).all()
        assert {row.remindKind for row in reminder_rows} == {
            "plan_start_10m",
            "plan_end_10m",
        }
        assert list_reminder_events(db) == []
    finally:
        db.close()


def test_standalone_reminder_can_be_created_listed_and_updated() -> None:
    db = _session()
    try:
        created = create_reminder_event(
            db,
            title="Bring ID",
            triggerTime="2026-09-15T07:30:00+08:00",
        )
        assert created["standalone"] is True
        assert created["triggerTime"].startswith("2026-09-15T07:30:00")
        assert [item["evtId"] for item in list_reminder_events(db)] == [created["evtId"]]

        updated = update_reminder_event(
            db,
            created["evtId"],
            title="Bring student ID",
            triggerTime="2026-09-15T07:45:00+08:00",
        )
        assert updated["title"] == "Bring student ID"
        assert updated["triggerTime"].startswith("2026-09-15T07:45:00")
    finally:
        db.close()


def test_ddl_defaults_to_two_plans_and_can_replace_with_multiple_plans() -> None:
    db = _session()
    try:
        ddl = create_ddl_event(
            db,
            title="Submit report",
            endTime="2026-09-20T20:00:00+08:00",
        )
        assert len(ddl["plans"]) == 2
        assert {item["planRole"] for item in ddl["plans"]} == {
            "one_day_before",
            "one_hour_before",
        }

        first = ddl["plans"][0]
        updated = replace_ddl_plans(
            db,
            ddl["evtId"],
            [
                {
                    "planEvtId": first["evtId"],
                    "planRole": "one_day_before",
                    "title": "Outline report",
                    "stTime": "2026-09-19T20:00:00+08:00",
                    "durationMin": 45,
                },
                {
                    "planRole": "manual",
                    "title": "Check figures",
                    "stTime": "2026-09-20T16:00:00+08:00",
                    "durationMin": 30,
                },
                {
                    "planRole": "manual",
                    "title": "Final proofread",
                    "stTime": "2026-09-20T18:30:00+08:00",
                    "durationMin": 30,
                },
            ],
        )
        assert len(updated["plans"]) == 3
        assert [item["title"] for item in updated["plans"]] == [
            "Outline report",
            "Check figures",
            "Final proofread",
        ]
        assert len(get_event(db, ddl["evtId"])["plans"]) == 3
    finally:
        db.close()
