from fastapi.testclient import TestClient

from app.main import create_app


def test_device_pair_api_requires_two_sided_confirmation(app_env) -> None:
    client = TestClient(create_app())
    assert client.post("/api/auth/setup", json={"password": "correct-horse-battery-staple"}).status_code == 200
    started = client.post("/api/device/pair/start", json={"deviceName": "Desk screen", "deviceKind": "screen"})
    assert started.status_code == 200
    pair = started.json()["data"]
    pair_id = pair["pairId"]
    assert client.post(f"/api/device/pair/{pair_id}/claim", json={"claimCode": pair["claimCode"]}).json()["data"]["stat"] == "claimed"
    assert client.post(f"/api/device/pair/{pair_id}/confirm").json()["data"]["stat"] == "userConfirmed"
    activated = client.post(f"/api/device/pair/{pair_id}/activate", json={"claimCode": pair["claimCode"]})
    token = activated.json()["data"]["deviceToken"]
    device_id = activated.json()["data"]["device"]["deviceId"]
    dispatched = client.post("/api/device/dispatch", json={"deviceId": device_id, "kind": "notify", "payload": {"title": "Focus"}})
    assert dispatched.status_code == 200
    pulled = client.get("/api/device/dispatch", headers={"X-SmartCore-Device-Token": token})
    assert pulled.status_code == 200
    assert pulled.json()["data"][0]["userId"] == "default"
