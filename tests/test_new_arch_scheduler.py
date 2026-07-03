from app.db.session import SessionLocal, init_db
from app.new_core import crud
from app.new_core.scheduler import runReminderTick


def test_reminder_tick_routes_due_life_event_and_dedups(app_env) -> None:
    init_db()
    db = SessionLocal()
    try:
        crud.upsertDevState(db, devId="pi", state="working", confidence=0.95)
        event = crud.createLifeEvt(
            db,
            title="写报告",
            dueAt="2026-07-03T20:00:00+08:00",
            src="test",
        )

        first = runReminderTick(
            db,
            now="2026-07-03T20:00:00+08:00",
            screenOnline=True,
        )
        second = runReminderTick(
            db,
            now="2026-07-03T20:00:30+08:00",
            screenOnline=True,
        )
        logs = crud.listNotifyLog(db)
    finally:
        db.close()

    assert first["sent"] == 1
    assert second["sent"] == 0
    assert logs[-1]["channel"] == "screen"
    assert logs[-1]["dedupKey"] == f"lifeDue:{event['evtId']}"


def test_reminder_tick_routes_due_ddl_to_feishu_when_away(app_env) -> None:
    init_db()
    db = SessionLocal()
    try:
        crud.upsertDevState(db, devId="pi", state="away", confidence=0.95)
        event = crud.createDdlEvt(
            db,
            title="提交实验报告",
            ddlAt="2026-07-04T23:00:00+08:00",
            hardDdl=True,
            src="test",
        )

        result = runReminderTick(
            db,
            now="2026-07-04T23:00:00+08:00",
            screenOnline=True,
        )
        logs = crud.listNotifyLog(db)
    finally:
        db.close()

    assert result["sent"] == 1
    assert logs[-1]["channel"] == "feishu"
    assert logs[-1]["dedupKey"] == f"ddlDue:{event['evtId']}"
