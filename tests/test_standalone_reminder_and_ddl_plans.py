from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.server.api.ai_routes import _important_date_fallback, _normalize_event
from app.server.db.session import Base
from app.server.new_core.ddl_service import (
    create_ddl_event,
    replace_ddl_plans,
    replace_ddl_reminders,
)
from app.server.new_core.event_relations import cancel_event, create_plan_event, get_event
from app.server.new_core.models import ActLog, EvtBase, RemindEvt
from app.server.new_core.reminder_service import (
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

        create_log = db.scalar(
            select(ActLog).where(
                ActLog.targetId == created["evtId"],
                ActLog.action == "create",
            )
        )
        assert create_log is not None
        assert create_log.targetKind == "evt"

        updated = update_reminder_event(
            db,
            created["evtId"],
            title="Bring student ID",
            triggerTime="2026-09-15T07:45:00+08:00",
        )
        assert updated["title"] == "Bring student ID"
        assert updated["triggerTime"].startswith("2026-09-15T07:45:00")

        update_log = db.scalar(
            select(ActLog).where(
                ActLog.targetId == created["evtId"],
                ActLog.action == "update",
            )
        )
        assert update_log is not None
        assert update_log.targetKind == "evt"
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


def test_ddl_keeps_linked_reminders_separate_from_plans() -> None:
    db = _session()
    try:
        ddl = create_ddl_event(
            db,
            title="依依宝宝生日",
            endTime="2026-08-28T09:00:00+08:00",
            ddlReminders=[
                {"title": "买蛋糕", "triggerTime": "2026-08-27T09:00:00+08:00"},
                {"title": "买礼物", "triggerTime": "2026-08-23T09:00:00+08:00"},
            ],
        )
        assert [item["title"] for item in ddl["ddlReminders"]] == ["买礼物", "买蛋糕"]
        assert len(ddl["plans"]) == 2
        updated = replace_ddl_reminders(
            db,
            ddl["evtId"],
            [
                {
                    "remindEvtId": ddl["ddlReminders"][0]["evtId"],
                    "title": "买礼物",
                    "triggerTime": "2026-08-22T09:00:00+08:00",
                }
            ],
        )
        assert len(updated["ddlReminders"]) == 1
        assert updated["ddlReminders"][0]["triggerTime"].startswith("2026-08-22T09:00:00")
        cancelled = cancel_event(db, ddl["evtId"])
        assert cancelled["stat"] == "cancelled"
        linked = db.get(EvtBase, updated["ddlReminders"][0]["evtId"])
        assert linked is not None
        assert linked.stat == "cancelled"
    finally:
        db.close()


def test_important_date_fallback_keeps_explicit_relative_reminders() -> None:
    parsed = _important_date_fallback(
        "依依宝宝 2026 年 8 月 28 号过生日，提前一天需要提醒我买蛋糕，提前5天需要提醒我买礼物"
    )
    assert parsed is not None
    assert parsed["plans"] == []
    assert [(item["title"], item["triggerTime"]) for item in parsed["ddlReminders"]] == [
        ("买蛋糕", "2026-08-27T09:00:00+08:00"),
        ("买礼物", "2026-08-23T09:00:00+08:00"),
    ]


def test_ddl_with_reminders_does_not_gain_default_plans_when_model_omits_plans() -> None:
    parsed = _normalize_event(
        {
            "evtType": "ddl",
            "title": "生日准备",
            "endTime": "2026-08-28T09:00:00+08:00",
            "ddlReminders": [{"title": "买蛋糕", "triggerTime": "2026-08-27T09:00:00+08:00"}],
        }
    )
    assert parsed["plans"] == []
    assert [item["title"] for item in parsed["ddlReminders"]] == ["买蛋糕"]


def test_ddl_parser_preserves_an_explicit_empty_reminder_list() -> None:
    parsed = _normalize_event(
        {
            "evtType": "ddl",
            "title": "仅计划的截止事项",
            "endTime": "2026-08-28T09:00:00+08:00",
            "ddlReminders": [],
            "plans": [],
        }
    )
    assert parsed["ddlReminders"] == []
    assert parsed["plans"] == []
