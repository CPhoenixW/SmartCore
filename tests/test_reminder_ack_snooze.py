import json
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.db.session import SessionLocal, init_db
from app.main import create_app
from app.new_core import crud
from app.new_core.models import EvtBase, LifeEvt
from app.new_core.scheduler import runReminderTick

TZ = ZoneInfo("Asia/Shanghai")


def _card_action_event(action: str, evt_id: str, *, chat_id: str = "oc_default") -> dict:
    return {
        "schema": "2.0",
        "header": {"event_type": "card.action.trigger", "token": "verify-token"},
        "event": {
            "context": {"open_chat_id": chat_id},
            "operator": {"operator_id": {"open_id": "ou_user"}},
            "action": {
                "value": {
                    "kind": "smartcoreReminder",
                    "action": action,
                    "evtId": evt_id,
                }
            },
        },
    }


def test_reminder_done_marks_event_completed(app_env) -> None:
    init_db()
    db = SessionLocal()
    try:
        event = crud.createLifeEvt(
            db,
            title="交付周报",
            dueAt="2026-07-04T10:00:00+08:00",
            src="test",
        )
        result = crud.applyReminderAction(
            db,
            evtId=event["evtId"],
            action="done",
            now="2026-07-04T10:01:00+08:00",
            src="screen",
        )
        row = db.get(EvtBase, event["evtId"])
        life = db.get(LifeEvt, event["evtId"])
    finally:
        db.close()

    assert result["stat"] == "done"
    assert row is not None
    assert row.stat == "done"
    assert life is not None
    assert life.doneAt == "2026-07-04T10:01:00+08:00"


def test_reminder_snooze_moves_due_time_ten_minutes_and_can_remind_again(
    app_env,
    monkeypatch,
) -> None:
    init_db()
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.new_core.notify._sendFeishu",
        lambda title, content: (sent.append((title, content)) or (True, "chat", None)),
    )
    db = SessionLocal()
    try:
        crud.upsertDevState(db, devId="pi", state="away", confidence=0.9)
        event = crud.createLifeEvt(
            db,
            title="喝水",
            dueAt="2026-07-04T10:00:00+08:00",
            src="test",
        )
        first = runReminderTick(
            db,
            now="2026-07-04T10:00:10+08:00",
            screenOnline=False,
        )
        snoozed = crud.applyReminderAction(
            db,
            evtId=event["evtId"],
            action="snooze10",
            now="2026-07-04T10:00:30+08:00",
            src="feishu",
        )
        second = runReminderTick(
            db,
            now="2026-07-04T10:10:31+08:00",
            screenOnline=False,
        )
    finally:
        db.close()

    assert first["sent"] == 1
    assert snoozed["dueAt"] == "2026-07-04T10:10:30+08:00"
    assert second["sent"] == 1
    assert len(sent) == 2


def test_screen_reminder_action_api_updates_database(app_env) -> None:
    init_db()
    db = SessionLocal()
    try:
        event = crud.createLifeEvt(
            db,
            title="站会",
            dueAt="2026-07-04T10:00:00+08:00",
            src="test",
        )
    finally:
        db.close()

    client = TestClient(create_app())
    resp = client.post(
        "/api/reminder/action",
        json={
            "evtId": event["evtId"],
            "action": "snooze10",
            "now": "2026-07-04T10:05:00+08:00",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["dueAt"] == "2026-07-04T10:15:00+08:00"


def test_feishu_reminder_card_action_updates_event_without_openclaw_forward(
    app_env,
    monkeypatch,
) -> None:
    init_db()
    forwarded: list[dict] = []

    def fake_post(url, **kwargs):
        forwarded.append(kwargs["json"])

        class Resp:
            is_error = False
            status_code = 200

        return Resp()

    monkeypatch.setenv("OPENCLAW_EVENTS_ENDPOINT", "http://openclaw.local/events")
    monkeypatch.setattr("httpx.post", fake_post)
    db = SessionLocal()
    try:
        event = crud.createLifeEvt(
            db,
            title="提交材料",
            dueAt="2026-07-04T11:00:00+08:00",
            src="test",
        )
    finally:
        db.close()

    client = TestClient(create_app())
    resp = client.post(
        "/feishu/event",
        content=json.dumps(_card_action_event("reminderDone", event["evtId"])),
        headers={"Content-Type": "application/json"},
    )

    assert resp.status_code == 200
    assert resp.json()["toast"]["type"] == "success"
    assert forwarded == []

    db = SessionLocal()
    try:
        row = db.get(EvtBase, event["evtId"])
    finally:
        db.close()
    assert row is not None
    assert row.stat == "done"


def test_feishu_reminder_card_contains_done_and_snooze_buttons(app_env, monkeypatch) -> None:
    captured: dict = {}
    now = datetime(2026, 7, 4, 10, 0, tzinfo=TZ)

    class FakeClient:
        def send_interactive_card(self, receive_id, card):
            captured["receive_id"] = receive_id
            captured["card"] = card
            return {"code": 0, "data": {"message_id": "om_card"}}

    monkeypatch.setattr("app.new_core.notify._getFeishuClient", lambda: FakeClient())
    monkeypatch.setenv("FEISHU_DEFAULT_CHAT_ID", "oc_default")
    init_db()
    db = SessionLocal()
    try:
        event = crud.createLifeEvt(
            db,
            title="吃药",
            dueAt=now.isoformat(),
            src="test",
        )
        result = crud.sendReminder(
            db,
            evtId=event["evtId"],
            title=event["title"],
            content=event["dueAt"],
            channel="feishu",
            dedupKey=f"lifeDue:{event['evtId']}:{event['dueAt']}",
        )
    finally:
        db.close()

    card_text = json.dumps(captured["card"], ensure_ascii=False)
    assert result["stat"] == "sent"
    assert "已完成" in card_text
    assert "延时 10 分钟" in card_text
    assert "reminderDone" in card_text
    assert "reminderSnooze10" in card_text
    assert event["evtId"] in card_text
