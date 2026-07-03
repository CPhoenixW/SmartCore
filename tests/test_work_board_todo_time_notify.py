from fastapi.testclient import TestClient

from app.db.session import SessionLocal, init_db
from app.main import create_app
from app.new_core import crud
from app.new_core.notify import routeNotify


def test_work_board_prioritizes_todo_and_collapses_done_cancelled(app_env) -> None:
    client = TestClient(create_app())
    html = client.get("/work").text
    css = client.get("/static/work/work.css").text
    js = client.get("/static/work/work.js").text

    assert "evt-board-layout" in html
    assert "todo-focus" in html
    assert "evtArchiveDetails" in html
    assert "evt-archive-grid" in html
    assert "open = doneCount + cancelledCount > 0 && todoCount === 0" in js
    assert ".todo-focus" in css
    assert ".evt-archive-grid" in css
    assert ".archive-panel" in css
    assert "grid-template-columns: minmax(0, 1fr)" in css


def test_evt_detail_drawer_can_edit_type_specific_time(app_env) -> None:
    client = TestClient(create_app())
    html = client.get("/work").text
    js = client.get("/static/work/work.js").text

    assert 'id="evtTimeField"' in html
    assert 'name="evtTime"' in html
    assert 'function toLocalInputValue' in js
    assert 'function evtTimeFieldName' in js
    assert 'function syncEvtTimeField' in js
    assert 'dueAt' in js
    assert 'ddlAt' in js
    assert 'classDate' in js

    init_db()
    db = SessionLocal()
    try:
        event = crud.createLifeEvt(
            db,
            title="改时间",
            dueAt="2026-07-05T20:00:00+08:00",
            src="test",
        )
        updated = crud.updateEvt(db, event["evtId"], dueAt="2026-07-06T21:30:00+08:00")
    finally:
        db.close()

    assert updated["dueAt"] == "2026-07-06T21:30:00+08:00"


def test_notify_router_performs_real_delivery_and_records_failures(app_env, monkeypatch) -> None:
    init_db()
    db = SessionLocal()
    sent: list[dict] = []

    def fake_screen(message: dict) -> bool:
        sent.append(message)
        return True

    monkeypatch.setattr("app.new_core.notify.screenManager.broadcastFromThread", fake_screen)
    try:
        crud.upsertDevState(db, devId="pi", state="working", confidence=0.9)
        result = routeNotify(
            db,
            title="下一项",
            content="20:00 写报告",
            screenOnline=True,
            dedupKey="unit:screen",
        )
        logs = crud.listNotifyLog(db)
    finally:
        db.close()

    assert result["channel"] == "screen"
    assert result["stat"] == "sent"
    assert sent == [{"kind": "reminder", "title": "下一项", "content": "20:00 写报告"}]
    assert logs[-1]["dedupKey"] == "unit:screen"


def test_notify_router_sends_feishu_when_away(app_env, monkeypatch) -> None:
    init_db()
    db = SessionLocal()
    texts: list[tuple[str, str]] = []

    class FakeClient:
        def send_text(self, receive_id: str, text: str) -> dict:
            texts.append((receive_id, text))
            return {"code": 0}

    class FakeSettings:
        feishu_app_id = "app"
        feishu_app_secret = "secret"
        feishu_default_chat_id = "chat"

    monkeypatch.setattr("app.new_core.notify._feishuClient", None)
    monkeypatch.setattr("app.new_core.notify.get_settings", lambda: FakeSettings())
    monkeypatch.setattr("app.new_core.notify.FeishuClient", lambda app_id, app_secret: FakeClient())
    try:
        crud.upsertDevState(db, devId="pi", state="away", confidence=0.9)
        result = routeNotify(
            db,
            title="提醒",
            content="记得喝水",
            screenOnline=True,
            dedupKey="unit:feishu",
        )
        logs = crud.listNotifyLog(db)
    finally:
        db.close()

    assert result["channel"] == "feishu"
    assert result["stat"] == "sent"
    assert texts == [("chat", "提醒\n记得喝水")]
    assert logs[-1]["dedupKey"] == "unit:feishu"
