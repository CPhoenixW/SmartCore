from fastapi.testclient import TestClient

from app.auth.security import create_session_token, decode_session_actor_id, decode_session_token
from app.db.session import SessionLocal
from app.main import create_app
from app.new_core.models import AppUser


def test_admin_switch_keeps_actor_identity(app_env) -> None:
    app = create_app()
    db = SessionLocal()
    try:
        db.add(AppUser(userId="other", loginName="other", displayName="Other", role="user"))
        db.commit()
    finally:
        db.close()
    client = TestClient(app)
    assert client.post("/api/auth/setup", json={"password": "correct-horse-battery-staple"}).status_code == 200
    response = client.post("/api/admin/activeUser", json={"userId": "other"})
    assert response.status_code == 200
    token = client.cookies.get("smartcore_session")
    assert decode_session_token(token) == "other"
    assert decode_session_actor_id(token) == "default"
    assert client.get("/api/admin/users").status_code == 200


def test_event_api_rejects_cross_user_access(app_env) -> None:
    app = create_app()
    db = SessionLocal()
    try:
        db.add(AppUser(userId="other", loginName="other", displayName="Other", role="user"))
        db.commit()
    finally:
        db.close()
    client = TestClient(app)
    client.cookies.clear()
    default_cookie = {"Cookie": f"smartcore_session={create_session_token(chr(100)+chr(101)+chr(102)+chr(97)+chr(117)+chr(108)+chr(116))}"}
    created = client.post("/api/planEvt", headers=default_cookie, json={"title": "Private", "stTime": "2026-07-14T09:00:00+08:00"})
    assert created.status_code == 200
    evt_id = created.json()["data"]["evtId"]
    other = TestClient(app)
    other.cookies.set("smartcore_session", create_session_token("other"))
    assert other.get(f"/api/evt/{evt_id}").status_code == 404
    assert other.patch(f"/api/evt/{evt_id}", json={"title": "stolen"}).status_code == 404


def test_heartbeat_requires_paired_device_credential(app_env) -> None:
    client = TestClient(create_app())
    assert client.post("/api/auth/setup", json={"password": "correct-horse-battery-staple"}).status_code == 200
    pair = client.post("/api/device/pair/start", json={"deviceName": "Pi", "deviceKind": "pi"}).json()["data"]
    assert client.post(f"/api/device/pair/{pair['pairId']}/claim", json={"claimCode": pair["claimCode"]}).status_code == 200
    assert client.post(f"/api/device/pair/{pair['pairId']}/confirm").status_code == 200
    activated = client.post(f"/api/device/pair/{pair['pairId']}/activate", json={"claimCode": pair["claimCode"]}).json()["data"]
    body = {"devId": activated["device"]["deviceId"], "currentTime": "2026-07-14T09:00:00+08:00", "present": True, "stateConfidence": 0.9}
    assert client.post("/dev/heartbeat", json=body).status_code == 401
    assert client.post("/dev/heartbeat", json=body, headers={"X-SmartCore-Device-Token": activated["deviceToken"]}).status_code == 200
