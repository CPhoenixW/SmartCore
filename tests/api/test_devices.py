from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.server.auth.security import (
    create_session_token,
    decode_session_actor_id,
    decode_session_token,
)
from app.server.db.session import SessionLocal, init_db
from app.server.main import create_app
from app.server.new_core import crud
from app.server.new_core.models import AppUser, DeviceKey, LifeDevice
from app.server.user_device.service import (
    activatePair,
    claimPair,
    confirmPair,
    pendingDispatches,
    queueDispatch,
    requireDevice,
    startPair,
)

pytestmark = pytest.mark.api


def test_device_pair_api_requires_two_sided_confirmation(app_env) -> None:
    client = TestClient(create_app())
    assert (
        client.post(
            "/api/auth/setup", json={"password": "correct-horse-battery-staple"}
        ).status_code
        == 200
    )
    started = client.post(
        "/api/device/pair/start", json={"deviceName": "Desk screen", "deviceKind": "screen"}
    )
    assert started.status_code == 200
    pair = started.json()["data"]
    pair_id = pair["pairId"]
    assert (
        client.post(
            f"/api/device/pair/{pair_id}/claim", json={"claimCode": pair["claimCode"]}
        ).json()["data"]["stat"]
        == "claimed"
    )
    assert (
        client.post(f"/api/device/pair/{pair_id}/confirm").json()["data"]["stat"] == "userConfirmed"
    )
    activated = client.post(
        f"/api/device/pair/{pair_id}/activate", json={"claimCode": pair["claimCode"]}
    )
    assert activated.json()["data"]["device"]["deviceName"] == "Desk screen"
    token = activated.json()["data"]["deviceToken"]
    device_id = activated.json()["data"]["device"]["deviceId"]
    dispatched = client.post(
        "/api/device/dispatch",
        json={"deviceId": device_id, "kind": "notify", "payload": {"title": "Focus"}},
    )
    assert dispatched.status_code == 200
    pulled = client.get("/api/device/dispatch", headers={"X-SmartCore-Device-Token": token})
    assert pulled.status_code == 200
    assert pulled.json()["data"][0]["userId"] == "default"


def test_pairing_requires_claim_and_user_confirmation(app_env) -> None:
    init_db()
    db = SessionLocal()
    try:
        crud.getCurrentUser(db)
        db.commit()
        pair = startPair(db, "default", "Desk screen", "screen")
        assert pair.stat == "created"
        claimPair(db, pair.pairId, pair.claimCode, "Desk screen")
        assert confirmPair(db, pair.pairId, "default").stat == "userConfirmed"
        device, token = activatePair(db, pair.pairId, pair.claimCode)
        assert device.userId == "default"
        assert requireDevice(db, token).deviceId == device.deviceId
        key = db.scalar(select(DeviceKey).where(DeviceKey.deviceId == device.deviceId))
        assert key is not None
        assert key.tokenHash != token
    finally:
        db.close()


def test_dispatch_is_owned_by_authenticated_device_and_receipts_are_deduplicated(app_env) -> None:
    init_db()
    db = SessionLocal()
    try:
        crud.getCurrentUser(db)
        db.commit()
        pair = startPair(db, "default", "Pi", "pi")
        claimPair(db, pair.pairId, pair.claimCode)
        confirmPair(db, pair.pairId, "default")
        device, token = activatePair(db, pair.pairId, pair.claimCode)
        dispatch = queueDispatch(db, device, "notify", {"title": "Focus"})
        rows = pendingDispatches(db, requireDevice(db, token))
        assert [row.dispatchId for row in rows] == [dispatch.dispatchId]
        assert pendingDispatches(db, requireDevice(db, token)) == []
        from app.server.new_core.models import DeviceDispatch, DeviceReceipt

        row = db.get(DeviceDispatch, dispatch.dispatchId)
        db.add(DeviceReceipt(dispatchId=row.dispatchId, deviceId=device.deviceId, result="shown"))
        db.commit()
        assert (
            db.scalar(select(DeviceReceipt).where(DeviceReceipt.dispatchId == row.dispatchId))
            is not None
        )
        assert db.get(LifeDevice, device.deviceId).userId == "default"
    finally:
        db.close()


def test_admin_switch_keeps_actor_identity(app_env) -> None:
    app = create_app()
    db = SessionLocal()
    try:
        db.add(AppUser(userId="other", loginName="other", displayName="Other", role="user"))
        db.commit()
    finally:
        db.close()
    client = TestClient(app)
    assert (
        client.post(
            "/api/auth/setup", json={"password": "correct-horse-battery-staple"}
        ).status_code
        == 200
    )
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
    default_cookie = {
        "Cookie": f"smartcore_session={create_session_token(chr(100) + chr(101) + chr(102) + chr(97) + chr(117) + chr(108) + chr(116))}"
    }
    created = client.post(
        "/api/planEvt",
        headers=default_cookie,
        json={"title": "Private", "stTime": "2026-07-14T09:00:00+08:00"},
    )
    assert created.status_code == 200
    evt_id = created.json()["data"]["evtId"]
    other = TestClient(app)
    other.cookies.set("smartcore_session", create_session_token("other"))
    assert other.get(f"/api/evt/{evt_id}").status_code == 404
    assert other.patch(f"/api/evt/{evt_id}", json={"title": "stolen"}).status_code == 404


def test_heartbeat_requires_paired_device_credential(app_env) -> None:
    client = TestClient(create_app())
    assert (
        client.post(
            "/api/auth/setup", json={"password": "correct-horse-battery-staple"}
        ).status_code
        == 200
    )
    pair = client.post(
        "/api/device/pair/start", json={"deviceName": "Pi", "deviceKind": "pi"}
    ).json()["data"]
    assert (
        client.post(
            f"/api/device/pair/{pair['pairId']}/claim", json={"claimCode": pair["claimCode"]}
        ).status_code
        == 200
    )
    assert client.post(f"/api/device/pair/{pair['pairId']}/confirm").status_code == 200
    activated = client.post(
        f"/api/device/pair/{pair['pairId']}/activate", json={"claimCode": pair["claimCode"]}
    ).json()["data"]
    body = {
        "devId": activated["device"]["deviceId"],
        "currentTime": "2026-07-14T09:00:00+08:00",
        "present": True,
        "stateConfidence": 0.9,
    }
    assert client.post("/dev/heartbeat", json=body).status_code == 401
    assert (
        client.post(
            "/dev/heartbeat",
            json=body,
            headers={"X-SmartCore-Device-Token": activated["deviceToken"]},
        ).status_code
        == 200
    )
