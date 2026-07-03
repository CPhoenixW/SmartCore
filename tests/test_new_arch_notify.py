from app.db.session import SessionLocal, init_db
from app.new_core import crud
from app.new_core.notify import routeNotify


def test_notify_router_uses_screen_when_working_and_screen_online(app_env) -> None:
    init_db()
    db = SessionLocal()
    try:
        crud.upsertDevState(db, devId="pi", state="working", confidence=0.9)
        result = routeNotify(
            db,
            title="下一项",
            content="20:00 写报告",
            screenOnline=True,
        )
        logs = crud.listNotifyLog(db)
    finally:
        db.close()

    assert result["channel"] == "screen"
    assert result["stat"] == "sent"
    assert logs[-1]["channel"] == "screen"


def test_notify_router_falls_back_to_feishu_when_screen_offline(app_env) -> None:
    init_db()
    db = SessionLocal()
    try:
        crud.upsertDevState(db, devId="pi", state="working", confidence=0.9)
        result = routeNotify(
            db,
            title="下一项",
            content="20:00 写报告",
            screenOnline=False,
        )
    finally:
        db.close()

    assert result["channel"] == "feishu"
    assert result["stat"] == "fallback"


def test_notify_router_uses_feishu_when_away_or_unknown(app_env) -> None:
    init_db()
    db = SessionLocal()
    try:
        crud.upsertDevState(db, devId="pi", state="away", confidence=0.9)
        away = routeNotify(db, title="提醒", content="记得回看", screenOnline=True)
        crud.upsertDevState(db, devId="pi", state="unknown", confidence=None)
        unknown = routeNotify(db, title="提醒", content="状态未知", screenOnline=True)
    finally:
        db.close()

    assert away["channel"] == "feishu"
    assert away["stat"] == "sent"
    assert unknown["channel"] == "feishu"
    assert unknown["stat"] == "sent"
