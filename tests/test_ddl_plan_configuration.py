from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.server.db.session import Base
from app.server.new_core import crud
from app.server.new_core.ddl_service import create_ddl_event
from app.server.new_core.models import DdlPlan, EvtBase  # noqa: F401


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    script = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "server"
        / "db"
        / "sql"
        / "device_photo_request.sql"
    ).read_text(encoding="utf-8")
    raw = engine.raw_connection()
    try:
        raw.executescript(script)
        raw.commit()
    finally:
        raw.close()
    return Session(engine)


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
