from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.server.agent.relation_query_routes import _relation_tools, createRelationQueryRouter
from app.server.api.ai_routes import _important_date_fallback, _normalize_event
from app.server.db.session import Base
from app.server.new_core import crud, event_relations, scheduler
from app.server.new_core.ddl_service import (
    create_ddl_event,
    replace_ddl_plans,
    replace_ddl_reminders,
)
from app.server.new_core.event_relations import (
    cancel_event,
    create_course_event,
    create_plan_event,
    expand_course_dates,
    get_event,
    list_events,
    update_course_event,
    update_commute_plan,
    update_event,
)
from app.server.new_core.models import (  # noqa: F401
    ActLog,
    AppUser,  # noqa: F401
    CoursePlan,
    DdlPlan,
    EvtBase,
    PlanEvt,
    RemindEvt,
)
from app.server.new_core.preferences import (
    UserPreference,  # noqa: F401
    get_user_preferences,
    update_user_preferences,
)
from app.server.new_core.relation_maintenance import ensure_missing_relations
from app.server.new_core.reminder_service import (
    create_reminder_event,
    list_reminder_events,
    update_reminder_event,
)

pytestmark = pytest.mark.unit


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return Session(engine)


def test_weekday_names_expand_to_matching_dates() -> None:
    dates = expand_course_dates(
        st_date="2026-09-01",
        end_date="2026-09-30",
        week_day="星期二",
        week_mode="all",
    )
    assert [value.isoformat() for value in dates] == [
        "2026-09-01",
        "2026-09-08",
        "2026-09-15",
        "2026-09-22",
        "2026-09-29",
    ]


def test_course_creates_one_plan_per_class_and_two_reminders_per_plan() -> None:
    db = _session()
    try:
        course = create_course_event(
            db,
            courseName="Robotics",
            teacher="Teacher Wang",
            location="A101",
            stTime="08:00",
            endTime="09:40",
            stDate="2026-09-01",
            endDate="2026-09-15",
            weekDay="星期二",
        )

        assert course["weekDay"] == 2
        assert course["occurrenceCount"] == 3
        assert [plan["occurrenceDate"] for plan in course["plans"]] == [
            "2026-09-01",
            "2026-09-08",
            "2026-09-15",
        ]
        assert all(plan["durationMin"] == 100 for plan in course["plans"])
        assert all(len(plan["reminders"]) == 2 for plan in course["plans"])
        assert (
            db.scalar(select(CoursePlan).where(CoursePlan.courseEvtId == course["evtId"]))
            is not None
        )
        assert len(db.scalars(select(RemindEvt)).all()) == 6
    finally:
        db.close()


def test_updating_course_regenerates_occurrences_without_duplicates() -> None:
    db = _session()
    try:
        course = create_course_event(
            db,
            courseName="Math",
            stTime="10:00",
            endTime="11:30",
            stDate="2026-09-01",
            endDate="2026-09-30",
            weekDay=2,
        )
        updated = update_course_event(
            db,
            course["evtId"],
            weekDay=4,
            stTime="14:00",
            endTime="15:30",
        )

        assert updated["weekDay"] == 4
        assert [plan["occurrenceDate"] for plan in updated["plans"]] == [
            "2026-09-03",
            "2026-09-10",
            "2026-09-17",
            "2026-09-24",
        ]
        assert len({plan["evtId"] for plan in updated["plans"]}) == 4
        assert all(plan["stTime"].endswith("14:00:00+08:00") for plan in updated["plans"])
        assert len(db.scalars(select(RemindEvt)).all()) == 8
    finally:
        db.close()


def test_day_view_contains_course_plan_but_not_course_template_or_reminders() -> None:
    db = _session()
    try:
        create_course_event(
            db,
            courseName="Physics",
            stTime="08:00",
            endTime="09:00",
            stDate="2026-09-07",
            endDate="2026-09-07",
            weekDay=1,
        )
        rows = list_events(
            db,
            date_value="2026-09-07",
            include_course_templates=False,
        )
        assert len(rows) == 1
        assert rows[0]["evtType"] == "plan"
        assert rows[0]["generatedBy"] == "course"
        assert rows[0]["courseName"] == "Physics"
    finally:
        db.close()


def test_time_range_query_handles_course_clock_fields() -> None:
    db = _session()
    try:
        create_course_event(
            db,
            courseName="Internship",
            stTime="10:00",
            endTime="19:00",
            stDate="2026-07-13",
            endDate="2026-08-14",
            weekDay=5,
        )
        rows = list_events(
            db,
            start="2026-07-17T00:00:00+08:00",
            end="2026-07-17T23:59:59+08:00",
        )
        assert {row["evtType"] for row in rows} == {"course", "plan"}
        assert any(row["evtType"] == "course" and row["title"] == "Internship" for row in rows)

        calendar_rows = list_events(
            db,
            start="2026-07-17T00:00:00+08:00",
            end="2026-07-17T23:59:59+08:00",
            include_course_templates=False,
        )
        assert len(calendar_rows) == 1
        assert calendar_rows[0]["evtType"] == "plan"
        assert calendar_rows[0]["title"] == "Internship"
    finally:
        db.close()


def test_create_ddl_with_adjusted_linked_plans() -> None:
    db = _session()
    try:
        ddl = create_ddl_event(
            db,
            title="提交课程报告",
            endTime="2026-07-10T20:00:00+08:00",
            plans=[
                {
                    "planRole": "one_day_before",
                    "stTime": "2026-07-09T18:30:00+08:00",
                    "durationMin": 45,
                },
                {
                    "planRole": "one_hour_before",
                    "stTime": "2026-07-10T18:45:00+08:00",
                    "durationMin": 20,
                },
            ],
        )

        assert ddl["evtType"] == "ddl"
        assert [plan["planRole"] for plan in ddl["plans"]] == [
            "one_day_before",
            "one_hour_before",
        ]
        assert ddl["plans"][0]["stTime"] == "2026-07-09T18:30:00+08:00"
        assert ddl["plans"][0]["durationMin"] == 45
        assert ddl["plans"][1]["durationMin"] == 20
    finally:
        db.close()


def test_cancelling_ddl_cancels_all_linked_plans() -> None:
    db = _session()
    try:
        ddl = create_ddl_event(
            db,
            title="提交课程报告",
            endTime="2026-07-10T20:00:00+08:00",
        )
        linked_ids = [plan["evtId"] for plan in ddl["plans"]]

        crud.cancelEvt(db, ddl["evtId"])

        assert db.get(EvtBase, ddl["evtId"]).stat == "cancelled"
        assert linked_ids
        assert all(db.get(EvtBase, plan_id).stat == "cancelled" for plan_id in linked_ids)
    finally:
        db.close()


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


def test_missing_relation_backfill_does_not_overwrite_customized_occurrence() -> None:
    db = _session()
    try:
        course = create_course_event(
            db,
            courseName="Control Theory",
            stTime="08:00",
            endTime="09:30",
            stDate="2026-09-01",
            endDate="2026-09-08",
            weekDay="Tuesday",
        )
        first_plan = course["plans"][0]
        update_event(
            db,
            first_plan["evtId"],
            stTime="2026-09-01T10:00:00+08:00",
            durationMin=120,
        )

        before = db.get(PlanEvt, first_plan["evtId"])
        assert before is not None
        assert before.stTime == "2026-09-01T10:00:00+08:00"
        assert before.durationMin == 120

        ensure_missing_relations(db)

        after = db.get(PlanEvt, first_plan["evtId"])
        assert after is not None
        assert after.stTime == "2026-09-01T10:00:00+08:00"
        assert after.durationMin == 120
        assert len(db.scalars(select(CoursePlan)).all()) == 2
        assert len(db.scalars(select(RemindEvt)).all()) == 4
    finally:
        db.close()


def test_openclaw_tools_publish_course_and_reminder_relations() -> None:
    tools = _relation_tools()
    by_name = {tool["name"]: tool for tool in tools}
    query_properties = by_name["evtQuery"]["inputSchema"]["properties"]
    create_properties = by_name["evtCreate"]["inputSchema"]["properties"]

    assert query_properties["includeLinkedPlans"]["default"] is True
    assert query_properties["includeReminders"]["default"] is False
    assert "weekDay" in create_properties
    assert "weekMode" in create_properties

    paths = {route.path for route in createRelationQueryRouter().routes}
    assert "/agent/tools" in paths
    assert "/agent/db/query_events" in paths
    assert "/agent/evtQuery" in paths


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


def test_commute_update_uses_arrival_for_plan_and_reuses_manual_reminder() -> None:
    db = _session()
    try:
        plan = create_plan_event(
            db,
            title="晚间工作",
            stTime="2026-08-01T14:00:00+08:00",
            durationMin=480,
        )
        reminder = create_reminder_event(
            db,
            title="出发",
            triggerTime="2026-08-01T08:30:00+08:00",
        )
        reminder_count = len(db.scalars(select(RemindEvt)).all())

        result = update_commute_plan(
            db,
            plan_evt_id=plan["evtId"],
            reminder_evt_id=reminder["evtId"],
            departure_at="2026-08-01T14:00:00+08:00",
            commute_minutes=90,
            end_at="2026-08-01T22:00:00+08:00",
            user_id="default",
            src="openclaw",
        )

        assert result["arrivalAt"] == "2026-08-01T15:30:00+08:00"
        assert result["plan"]["stTime"] == "2026-08-01T15:30:00+08:00"
        assert result["plan"]["durationMin"] == 390
        assert result["reminder"]["evtId"] == reminder["evtId"]
        assert result["reminder"]["triggerTime"] == "2026-08-01T14:00:00+08:00"
        assert len(db.scalars(select(RemindEvt)).all()) == reminder_count

        repeated = update_commute_plan(
            db,
            plan_evt_id=plan["evtId"],
            reminder_evt_id=reminder["evtId"],
            departure_at="2026-08-01T14:00:00+08:00",
            commute_minutes=90,
            end_at="2026-08-01T22:00:00+08:00",
            user_id="default",
            src="openclaw",
        )
        assert repeated["plan"]["durationMin"] == 390
        assert len(db.scalars(select(RemindEvt)).all()) == reminder_count
    finally:
        db.close()


def test_commute_update_rejects_cross_owner_and_linked_reminder() -> None:
    db = _session()
    try:
        plan = create_plan_event(
            db,
            title="通勤后工作",
            stTime="2026-08-01T15:00:00+08:00",
            durationMin=60,
        )
        reminder = create_reminder_event(
            db,
            title="出发",
            triggerTime="2026-08-01T13:00:00+08:00",
        )

        with pytest.raises(ValueError, match="plan not found"):
            update_commute_plan(
                db,
                plan_evt_id=plan["evtId"],
                reminder_evt_id=reminder["evtId"],
                departure_at="2026-08-01T14:00:00+08:00",
                commute_minutes=60,
                end_at="2026-08-01T18:00:00+08:00",
                user_id="other-user",
            )

        with pytest.raises(ValueError, match="standalone manual reminder"):
            update_commute_plan(
                db,
                plan_evt_id=plan["evtId"],
                reminder_evt_id=plan["reminders"][0]["evtId"],
                departure_at="2026-08-01T14:00:00+08:00",
                commute_minutes=60,
                end_at="2026-08-01T18:00:00+08:00",
                user_id="default",
            )

        with pytest.raises(ValueError, match="event is not a plan"):
            update_commute_plan(
                db,
                plan_evt_id=reminder["evtId"],
                reminder_evt_id=reminder["evtId"],
                departure_at="2026-08-01T14:00:00+08:00",
                commute_minutes=60,
                end_at="2026-08-01T18:00:00+08:00",
                user_id="default",
            )

        stored_plan = db.get(PlanEvt, plan["evtId"])
        stored_reminder = db.get(RemindEvt, reminder["evtId"])
        assert stored_plan is not None
        assert stored_plan.stTime == "2026-08-01T15:00:00+08:00"
        assert stored_reminder is not None
        assert stored_reminder.triggerTime == "2026-08-01T13:00:00+08:00"
    finally:
        db.close()


def test_commute_update_rolls_back_both_records_on_failure(monkeypatch) -> None:
    db = _session()
    try:
        plan = create_plan_event(
            db,
            title="原子更新",
            stTime="2026-08-01T10:00:00+08:00",
            durationMin=60,
        )
        reminder = create_reminder_event(
            db,
            title="原提醒",
            triggerTime="2026-08-01T09:00:00+08:00",
        )
        monkeypatch.setattr(
            event_relations,
            "sync_plan_reminders",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("forced failure")),
        )

        with pytest.raises(RuntimeError, match="forced failure"):
            update_commute_plan(
                db,
                plan_evt_id=plan["evtId"],
                reminder_evt_id=reminder["evtId"],
                departure_at="2026-08-01T12:00:00+08:00",
                commute_minutes=30,
                end_at="2026-08-01T15:00:00+08:00",
                user_id="default",
            )

        db.expire_all()
        stored_plan = db.get(PlanEvt, plan["evtId"])
        stored_reminder = db.get(RemindEvt, reminder["evtId"])
        assert stored_plan is not None
        assert stored_plan.stTime == "2026-08-01T10:00:00+08:00"
        assert stored_plan.durationMin == 60
        assert stored_reminder is not None
        assert stored_reminder.triggerTime == "2026-08-01T09:00:00+08:00"
    finally:
        db.close()
