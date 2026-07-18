import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


def _setup_client() -> TestClient:
    client = TestClient(create_app())
    assert client.post("/api/auth/setup", json={"password": "correct-horse-battery-staple"}).status_code == 200
    return client


def _paired_device(client: TestClient, kind: str) -> dict:
    pair = client.post("/api/device/pair/start", json={"deviceName": kind, "deviceKind": kind}).json()["data"]
    assert client.post(f"/api/device/pair/{pair['pairId']}/claim", json={"claimCode": pair["claimCode"]}).status_code == 200
    assert client.post(f"/api/device/pair/{pair['pairId']}/confirm").status_code == 200
    return client.post(f"/api/device/pair/{pair['pairId']}/activate", json={"claimCode": pair["claimCode"]}).json()["data"]


def test_register_creates_unprivileged_session(app_env) -> None:
    client = TestClient(create_app())
    response = client.post("/api/auth/register", json={"loginName": "phoenix", "displayName": "Phoenix", "password": "correct-horse-battery-staple"})
    assert response.status_code == 200
    assert response.json()["data"]["role"] == "user"
    assert client.get("/api/auth/me").json()["data"]["loginName"] == "phoenix"
    assert client.post("/api/auth/register", json={"loginName": "phoenix", "password": "correct-horse-battery-staple"}).status_code == 409


def test_login_name_session_uses_internal_user_id(app_env) -> None:
    client = TestClient(create_app())
    registered = client.post(
        "/api/auth/register",
        json={
            "loginName": "phoenix",
            "displayName": "Phoenix",
            "password": "correct-horse-battery-staple",
        },
    ).json()["data"]
    assert client.post("/api/auth/logout").status_code == 200

    logged_in = client.post(
        "/api/auth/login",
        json={"userId": "phoenix", "password": "correct-horse-battery-staple"},
    )
    assert logged_in.status_code == 200
    assert logged_in.json()["data"]["userId"] == registered["userId"]
    assert client.get("/api/auth/me").json()["data"]["userId"] == registered["userId"]

    profile = client.get("/api/user/me")
    assert profile.status_code == 200
    assert profile.json()["data"]["userId"] == registered["userId"]
    assert profile.json()["data"]["displayName"] == "Phoenix"

    event = client.post(
        "/api/planEvt",
        json={
            "title": "Normal user event",
            "stTime": "2026-07-18T10:00:00+08:00",
            "durationMin": 60,
        },
    )
    assert event.status_code == 200
    assert event.json()["data"]["userId"] == registered["userId"]

    assert client.post("/api/auth/logout").status_code == 200
    internal_id_login = client.post(
        "/api/auth/login",
        json={"userId": registered["userId"], "password": "correct-horse-battery-staple"},
    )
    assert internal_id_login.status_code == 200
    assert client.get("/api/user/me").json()["data"]["displayName"] == "Phoenix"


def test_paired_device_token_can_poll_photo_requests(app_env) -> None:
    client = _setup_client()
    activated = _paired_device(client, "pi")
    device_id = activated["device"]["deviceId"]
    token = activated["deviceToken"]
    assert client.post(f"/api/device/{device_id}/photoRequest", json={"reason": "test"}).status_code == 200
    assert client.get(f"/dev/photo/request?devId={device_id}", headers={"X-SmartCore-Device-Token": token}).status_code == 200
    assert client.get(f"/dev/photo/request?devId={device_id}").status_code == 401


def test_screen_websocket_requires_its_device_credential(app_env) -> None:
    client = _setup_client()
    activated = _paired_device(client, "screen")
    device_id = activated["device"]["deviceId"]
    token = activated["deviceToken"]
    with client.websocket_connect(f"/screen/ws?deviceId={device_id}&deviceToken={token}") as websocket:
        assert websocket.receive_json()["kind"] == "state"
    assert client.get("/screen/events", params={"deviceId": device_id}, headers={"X-SmartCore-Device-Token": token}).status_code == 200
    assert client.get("/screen/events", params={"deviceId": device_id}).status_code == 401


def test_deleted_device_token_is_revoked(app_env) -> None:
    client = _setup_client()
    activated = _paired_device(client, "screen")
    device_id = activated["device"]["deviceId"]
    token = activated["deviceToken"]
    assert client.delete(f"/api/device/{device_id}").status_code == 200
    assert client.get("/screen/events", params={"deviceId": device_id}, headers={"X-SmartCore-Device-Token": token}).status_code == 401


def test_feishu_binding_claims_then_confirms_chat(app_env, monkeypatch) -> None:
    client = _setup_client()
    bot = client.get("/api/admin/feishuBots").json()["data"][0]
    pair = client.post(f"/api/admin/feishuBots/{bot['botId']}/pair/start").json()["data"]
    monkeypatch.setenv("OPENCLAW_EVENTS_ENDPOINT", "http://openclaw.local/events")
    event = {
        "schema": "2.0",
        "header": {"event_type": "im.message.receive_v1", "token": "verify-token"},
        "event": {
            "sender": {"sender_id": {"open_id": "ou_bound"}, "sender_type": "user"},
            "message": {"message_id": "om_bind", "chat_id": "oc_bind", "chat_type": "p2p", "message_type": "text", "content": json.dumps({"text": f"绑定 {pair['claimCode']}"})},
        },
    }
    assert client.post("/feishu/event", json=event).status_code == 200
    confirmed = client.post(f"/api/admin/feishuBots/{bot['botId']}/pair/{pair['pairId']}/confirm")
    assert confirmed.status_code == 200
    assert confirmed.json()["data"]["stat"] == "active"


def test_same_feishu_identity_can_bind_two_chats_for_the_same_user(app_env, monkeypatch) -> None:
    client = _setup_client()
    bot = client.get("/api/admin/feishuBots").json()["data"][0]
    monkeypatch.setattr("app.feishu.client.FeishuClient.send_text", lambda *_args, **_kwargs: {"code": 0})

    for index, chat_id in enumerate(("oc_first", "oc_second"), start=1):
        pair = client.post(f"/api/admin/feishuBots/{bot['botId']}/pair/start").json()["data"]
        event = {
            "schema": "2.0",
            "header": {"event_type": "im.message.receive_v1", "token": "verify-token"},
            "event": {
                "sender": {"sender_id": {"open_id": "ou_same"}, "sender_type": "user"},
                "message": {"message_id": f"om_bind_{index}", "chat_id": chat_id, "chat_type": "p2p", "message_type": "text", "content": json.dumps({"text": f"绑定 {pair['claimCode']}"})},
            },
        }
        assert client.post("/feishu/event", json=event).status_code == 200
        assert client.post(f"/api/admin/feishuBots/{bot['botId']}/pair/{pair['pairId']}/confirm").status_code == 200


def test_important_date_natural_language_falls_back_to_a_ddl(app_env, monkeypatch) -> None:
    client = _setup_client()
    monkeypatch.setattr("app.api.ai_routes.complete_chat", lambda *_args, **_kwargs: "模型没有按要求输出")
    response = client.post("/api/llm/parse", json={
        "text": "依依宝宝2026年8月28号过生日，千万不能忘了给她准备礼物",
        "now": "2026-07-13T10:00:00+08:00",
    })
    assert response.status_code == 200
    parsed = response.json()["data"]["parsed"]
    assert parsed["evtType"] == "ddl"
    assert parsed["title"] == "依依宝宝生日礼物"
    assert parsed["prio"] == "high"
    assert parsed["hardDdl"] is True
    assert parsed["endTime"] == "2026-08-28T09:00:00+08:00"
    assert len(parsed["plans"]) == 2


@pytest.mark.parametrize(
    ("text", "raw", "expected_type", "time_key"),
    [
        ("明天晚上八点复习热流体，持续30分钟", '{"evtType":"plan","title":"复习热流体","prio":"mid","stTime":"2026-07-14T20:00:00+08:00","durationMin":30}', "plan", "stTime"),
        ("周五下午提醒我给导师发邮件", '{"evtType":"remind","title":"给导师发邮件","prio":"mid","triggerTime":"2026-07-17T15:00:00+08:00"}', "remind", "triggerTime"),
        ("下周一之前提交机器学习作业，务必完成", '{"evtType":"ddl","title":"提交机器学习作业","prio":"high","endTime":"2026-07-20T09:00:00+08:00","hardDdl":true}', "ddl", "endTime"),
    ],
)
def test_natural_language_event_shapes_are_loaded_into_the_form(app_env, monkeypatch, text, raw, expected_type, time_key) -> None:
    client = _setup_client()
    monkeypatch.setattr("app.api.ai_routes.complete_chat", lambda *_args, **_kwargs: raw)
    response = client.post("/api/llm/parse", json={"text": text, "now": "2026-07-13T10:00:00+08:00"})
    assert response.status_code == 200
    parsed = response.json()["data"]["parsed"]
    assert parsed["evtType"] == expected_type
    assert parsed["title"]
    assert parsed[time_key].endswith("+08:00")
