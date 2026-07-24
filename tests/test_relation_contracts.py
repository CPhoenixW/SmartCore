from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.server.agent.relation_query_routes import _relation_tools, createRelationQueryRouter
from app.server.db.session import Base
from app.server.new_core.event_relations import create_course_event, update_event
from app.server.new_core.models import CoursePlan, PlanEvt, RemindEvt
from app.server.new_core.relation_maintenance import ensure_missing_relations


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return Session(engine)


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
