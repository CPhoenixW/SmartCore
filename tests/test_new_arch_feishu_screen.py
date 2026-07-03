import json

from fastapi.testclient import TestClient

from app.main import create_app


def _message_event(text: str) -> dict:
    return {
        "schema": "2.0",
        "header": {"event_type": "im.message.receive_v1", "token": "verify-token"},
        "event": {
            "message": {
                "message_id": "om_1",
                "chat_id": "oc_1",
                "message_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            }
        },
    }


def test_feishu_message_is_logged_and_forwarded_to_openclaw(app_env, monkeypatch) -> None:
    forwarded = {}

    def fake_post(url, **kwargs):
        forwarded["url"] = url
        forwarded["json"] = kwargs["json"]

        class Resp:
            is_error = False
            status_code = 200

        return Resp()

    monkeypatch.setenv("OPENCLAW_EVENTS_ENDPOINT", "http://openclaw.local/events")
    monkeypatch.setattr("httpx.post", fake_post)
    client = TestClient(create_app())

    resp = client.post("/feishu/event", json=_message_event("今晚八点提醒我写报告"))

    assert resp.status_code == 200
    assert forwarded["json"]["eventType"] == "message"
    assert forwarded["json"]["message"]["text"] == "今晚八点提醒我写报告"
    assert client.get("/api/msgLog").json()["data"][0]["stat"] == "forwarded"


def test_screen_websocket_receives_initial_state_and_push(app_env) -> None:
    client = TestClient(create_app())

    with client.websocket_connect("/screen/ws") as ws:
        initial = ws.receive_json()
        assert initial["kind"] == "state"
        assert "serverNow" in initial

        pushed = client.post(
            "/agent/screenPush",
            headers={"X-SmartCore-Agent-Token": "agent-secret"},
            json={"title": "测试提醒", "content": "该看下一项了"},
        )
        assert pushed.status_code == 200
        message = ws.receive_json()
        assert message["kind"] == "reminder"
        assert message["title"] == "测试提醒"


def test_screen_websocket_sends_dev_state_after_connect(app_env) -> None:
    client = TestClient(create_app())
    client.post(
        "/dev/state",
        headers={"X-SmartCore-Device-Token": "device-secret"},
        json={"devId": "pi", "state": "working", "confidence": 0.88},
    )

    with client.websocket_connect("/screen/ws") as ws:
        initial = ws.receive_json()
        assert initial["kind"] == "state"

        dev_msg = ws.receive_json()
        assert dev_msg["kind"] == "devState"
        assert dev_msg["state"] == "working"
        assert dev_msg["devId"] == "pi"


def test_dev_state_broadcasts_to_connected_screen(app_env) -> None:
    client = TestClient(create_app())

    with client.websocket_connect("/screen/ws") as ws:
        assert ws.receive_json()["kind"] == "state"

        posted = client.post(
            "/dev/state",
            headers={"X-SmartCore-Device-Token": "device-secret"},
            json={"devId": "pi", "state": "away", "confidence": 0.91},
        )
        assert posted.status_code == 200

        dev_msg = ws.receive_json()
        assert dev_msg["kind"] == "devState"
        assert dev_msg["state"] == "away"
        assert dev_msg["devId"] == "pi"
