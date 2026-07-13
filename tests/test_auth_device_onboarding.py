import json

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


def test_feishu_binding_claims_then_confirms_device(app_env, monkeypatch) -> None:
    client = _setup_client()
    pair = client.post("/api/device/pair/start", json={"deviceName": "Feishu", "deviceKind": "feishuBot"}).json()["data"]
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
    assert client.get(f"/api/device/pair/{pair['pairId']}").json()["data"]["stat"] == "claimed"
    assert client.post(f"/api/device/pair/{pair['pairId']}/confirm").json()["data"]["stat"] == "paired"
    devices = client.get("/api/device").json()["data"]
    assert any(device["deviceKind"] == "feishuBot" for device in devices)
