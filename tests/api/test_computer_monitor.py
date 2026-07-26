from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.server.auth.security import create_session_token
from app.server.computer.service import cleanup_activity, monitor_status_dict
from app.server.db.session import SessionLocal
from app.server.main import create_app
from app.server.new_core.models import (
    AppUser,
    ComputerActivityBucket,
    ComputerActivityContext,
    ComputerDailyUsage,
    ComputerMonitorStatus,
    Device,
    EvtBase,
    PlanEvt,
)
from app.server.user_device.service import removeDevice
from tests.factories import pair_device

pytestmark = pytest.mark.api


def _bucket_start(minutes_ago: int = 1) -> datetime:
    return (datetime.now(UTC) - timedelta(minutes=minutes_ago)).replace(second=0, microsecond=0)


def _activity_payload(start: datetime, *, active: int = 45, idle: int = 15) -> dict:
    slices = [
        {
            "state": "active",
            "seconds": active,
            "bundleId": "com.apple.dt.Xcode",
            "appName": "Xcode",
            "windowTitle": "SmartCore - service.py",
            "contextKind": "ide",
            "workspace": "SmartCore",
            "documentName": "service.py",
            "titleRedacted": False,
        }
    ]
    if idle:
        slices.append({"state": "idle", "seconds": idle})
    return {
        "schemaVersion": 1,
        "buckets": [
            {
                "bucketStart": start.isoformat(),
                "timezone": "Asia/Singapore",
                "sessionId": "session-1",
                "coveredSeconds": active + idle,
                "switchCount": 2,
                "slices": slices,
            }
        ],
    }


def _setup_computer(client: TestClient) -> dict:
    client.post("/api/auth/setup", json={"password": "correct-horse-battery-staple"}).raise_for_status()
    return pair_device(client, name="Development Mac", kind="computer")


def test_stale_status_hides_last_application() -> None:
    last_heartbeat = (datetime.now(UTC) - timedelta(minutes=3)).isoformat()
    row = ComputerMonitorStatus(
        deviceId="computer",
        userId="user",
        currentState="active",
        currentAppName="Xcode",
        stateSince=(datetime.now(UTC) - timedelta(hours=1)).isoformat(),
        observedAt=last_heartbeat,
        lastHeartbeatAt=last_heartbeat,
    )
    status = monitor_status_dict(row)
    assert status is not None
    assert status["state"] == "offline"
    assert status["stateSince"] == last_heartbeat
    assert status["currentAppName"] is None


def test_computer_upload_is_device_owned_idempotent_and_reported(app_env) -> None:
    client = TestClient(create_app())
    paired = _setup_computer(client)
    token = paired["deviceToken"]
    device_id = paired["device"]["deviceId"]
    headers = {"X-SmartCore-Device-Token": token}

    db = SessionLocal()
    try:
        assert db.get(Device, device_id) is None
        start = _bucket_start()
        plan_base = EvtBase(userId="default", title="Implement monitor", evtType="plan")
        db.add(plan_base)
        db.flush()
        db.add(PlanEvt(evtId=plan_base.evtId, stTime=(start - timedelta(minutes=1)).isoformat(), durationMin=5))
        db.commit()
    finally:
        db.close()

    heartbeat = {
        "currentState": "active",
        "observedAt": datetime.now(UTC).isoformat(),
        "currentAppName": "Xcode",
        "currentWindowTitle": "SmartCore - service.py",
        "appVersion": "0.1.0",
        "osVersion": "macOS 26.4",
        "accessibilityGranted": True,
        "paused": False,
        "queueDepth": 1,
    }
    assert client.post("/api/computer/heartbeat", json=heartbeat).status_code == 401
    assert client.post("/api/computer/heartbeat", json=heartbeat, headers=headers).status_code == 200

    payload = _activity_payload(start)
    first = client.post("/api/computer/activity/batch", json=payload, headers=headers)
    assert first.status_code == 200
    assert first.json()["data"]["acceptedBucketStarts"] == [start.isoformat()]

    payload = _activity_payload(start, active=30, idle=30)
    second = client.post("/api/computer/activity/batch", json=payload, headers=headers)
    assert second.status_code == 200

    status = client.get("/api/computer/status", params={"deviceId": device_id})
    assert status.status_code == 200
    status_data = status.json()["data"]
    assert status_data["state"] == "active"
    assert status_data["currentWindowTitle"] == "SmartCore - service.py"
    assert status_data["analysis"]["state"] == "plan_active"
    assert status_data["analysis"]["currentPlan"]["title"] == "Implement monitor"
    assert status_data["analysis"]["reasonCodes"] == ["computer.active", "plan.current"]
    report = client.get(
        "/api/computer/usage",
        params={"deviceId": device_id, "range": "today", "timezone": "Asia/Singapore"},
    )
    assert report.status_code == 200
    data = report.json()["data"]
    assert data["totals"]["activeSeconds"] == 30
    assert data["totals"]["idleSeconds"] == 30
    assert data["totals"]["plannedActiveSeconds"] == 30
    assert data["daily"][0]["plannedActiveSeconds"] == 30
    assert data["totals"]["switchCount"] == 2
    assert data["sessions"][0]["sessionId"] == "session-1"
    assert data["sessions"][0]["inference"] is None
    assert data["applications"][0]["bundleId"] == "com.apple.dt.Xcode"
    assert data["titles"][0]["windowTitle"] == "SmartCore - service.py"
    assert data["titles"][0]["seconds"] == 30
    context = data["sessions"][0]["contexts"][0]
    assert context["windowTitle"] == "SmartCore - service.py"
    assert context["contextKind"] == "ide"
    assert context["workspace"] == "SmartCore"
    assert context["documentName"] == "service.py"

    rolling = client.get(
        "/api/computer/usage",
        params={"deviceId": device_id, "range": "24h", "timezone": "Asia/Singapore"},
    )
    assert rolling.status_code == 200
    rolling_data = rolling.json()["data"]
    rolling_start = datetime.fromisoformat(rolling_data["windowStart"])
    rolling_end = datetime.fromisoformat(rolling_data["windowEnd"])
    assert rolling_end - rolling_start == timedelta(hours=24)
    assert rolling_data["timeline"]
    assert rolling_data["sessions"] == []

    db = SessionLocal()
    try:
        assert len(list(db.scalars(select(ComputerActivityBucket)))) == 1
        daily = db.scalar(select(ComputerDailyUsage))
        assert daily is not None and daily.activeSeconds == 30
        stored_context = db.scalar(select(ComputerActivityContext))
        assert stored_context is not None and stored_context.windowTitle == "SmartCore - service.py"
    finally:
        db.close()


def test_computer_server_redacts_sensitive_context_even_when_client_does_not(app_env) -> None:
    client = TestClient(create_app())
    paired = _setup_computer(client)
    headers = {"X-SmartCore-Device-Token": paired["deviceToken"]}
    start = _bucket_start()
    payload = _activity_payload(start, active=60, idle=0)
    payload["buckets"][0]["slices"][0].update(
        bundleId="com.1password.1password",
        appName="1Password",
        windowTitle="Personal vault",
        contextKind="application",
        workspace="Private",
        documentName="vault",
    )

    response = client.post("/api/computer/activity/batch", json=payload, headers=headers)
    assert response.status_code == 200
    report = client.get(
        "/api/computer/usage",
        params={
            "deviceId": paired["device"]["deviceId"],
            "range": "today",
            "timezone": "Asia/Singapore",
        },
    ).json()["data"]
    context = report["sessions"][0]["contexts"][0]
    assert context["appName"] == "1Password"
    assert context["titleRedacted"] is True
    assert context["windowTitle"] is None
    assert context["workspace"] is None
    assert context["documentName"] is None
    assert report["titles"] == []


def test_computer_upload_rejects_full_urls_and_paths_in_structured_fields(app_env) -> None:
    client = TestClient(create_app())
    paired = _setup_computer(client)
    headers = {"X-SmartCore-Device-Token": paired["deviceToken"]}
    payload = _activity_payload(_bucket_start())
    context = payload["buckets"][0]["slices"][0]
    context["domain"] = "https://example.test/private"
    assert client.post("/api/computer/activity/batch", json=payload, headers=headers).status_code == 422

    context["domain"] = "example.test"
    context["workspace"] = "/Users/person/Private/SmartCore"
    assert client.post("/api/computer/activity/batch", json=payload, headers=headers).status_code == 422


def test_computer_routes_reject_wrong_device_kind_and_cross_owner(app_env) -> None:
    client = TestClient(create_app())
    computer = _setup_computer(client)
    pi = pair_device(client, name="Pi", kind="pi")
    payload = _activity_payload(_bucket_start())
    response = client.post(
        "/api/computer/activity/batch",
        json=payload,
        headers={"X-SmartCore-Device-Token": pi["deviceToken"]},
    )
    assert response.status_code == 403

    db = SessionLocal()
    try:
        db.add(AppUser(userId="other", loginName="other", displayName="Other", role="user"))
        db.commit()
    finally:
        db.close()
    other = TestClient(create_app())
    other.cookies.set("smartcore_session", create_session_token("other"))
    response = other.get(
        "/api/computer/usage",
        params={"deviceId": computer["device"]["deviceId"]},
    )
    assert response.status_code == 404


def test_computer_analysis_uses_fresh_owned_pi_presence(app_env) -> None:
    client = TestClient(create_app())
    computer = _setup_computer(client)
    pi = pair_device(client, name="Desk Pi", kind="pi")
    pi_heartbeat = {
        "devId": pi["device"]["deviceId"],
        "currentTime": datetime.now(UTC).isoformat(),
        "present": True,
        "persons": [],
        "stateConfidence": 0.9,
        "state": "working",
    }
    assert client.post(
        "/dev/heartbeat",
        json=pi_heartbeat,
        headers={"X-SmartCore-Device-Token": pi["deviceToken"]},
    ).status_code == 200

    computer_heartbeat = {
        "currentState": "idle",
        "observedAt": datetime.now(UTC).isoformat(),
        "appVersion": "0.2.0",
        "osVersion": "macOS",
        "queueDepth": 0,
    }
    assert client.post(
        "/api/computer/heartbeat",
        json=computer_heartbeat,
        headers={"X-SmartCore-Device-Token": computer["deviceToken"]},
    ).status_code == 200
    status = client.get(
        "/api/computer/status",
        params={"deviceId": computer["device"]["deviceId"]},
    ).json()["data"]
    assert status["analysis"]["state"] == "at_desk_inactive"
    assert status["analysis"]["presence"]["deviceId"] == pi["device"]["deviceId"]
    assert status["analysis"]["reasonCodes"] == ["computer.idle", "presence.present"]


def test_computer_upload_validation_and_retention_preserve_daily_summary(app_env) -> None:
    client = TestClient(create_app())
    paired = _setup_computer(client)
    headers = {"X-SmartCore-Device-Token": paired["deviceToken"]}
    start = _bucket_start()
    invalid = _activity_payload(start)
    invalid["buckets"][0]["coveredSeconds"] = 59
    assert client.post("/api/computer/activity/batch", json=invalid, headers=headers).status_code == 422
    assert client.post("/api/computer/activity/batch", json=_activity_payload(start), headers=headers).status_code == 200

    db = SessionLocal()
    try:
        bucket = db.scalar(select(ComputerActivityBucket))
        assert bucket is not None
        bucket.bucketStart = (datetime.now(UTC) - timedelta(days=91)).isoformat()
        db.commit()
        assert cleanup_activity(db, retention_days=90) == 1
        assert db.scalar(select(ComputerActivityBucket)) is None
        assert db.scalar(select(ComputerActivityContext)) is None
        assert db.scalar(select(ComputerDailyUsage)) is not None
    finally:
        db.close()


def test_overlapping_plans_use_union_for_total(app_env) -> None:
    client = TestClient(create_app())
    paired = _setup_computer(client)
    headers = {"X-SmartCore-Device-Token": paired["deviceToken"]}
    start = _bucket_start()
    db = SessionLocal()
    try:
        for title, offset in (("First", -1), ("Second", 0)):
            base = EvtBase(userId="default", title=title, evtType="plan")
            db.add(base)
            db.flush()
            db.add(PlanEvt(evtId=base.evtId, stTime=(start + timedelta(minutes=offset)).isoformat(), durationMin=3))
        db.commit()
    finally:
        db.close()

    assert client.post("/api/computer/activity/batch", json=_activity_payload(start, active=60, idle=0), headers=headers).status_code == 200
    data = client.get(
        "/api/computer/usage",
        params={"deviceId": paired["device"]["deviceId"], "range": "today", "timezone": "Asia/Singapore"},
    ).json()["data"]
    assert data["totals"]["plannedActiveSeconds"] == 60
    assert data["daily"][0]["plannedActiveSeconds"] == 60
    assert sum(plan["activeSeconds"] for plan in data["plans"]) == 120


def test_removing_computer_revokes_access_but_preserves_activity(app_env) -> None:
    client = TestClient(create_app())
    paired = _setup_computer(client)
    device_id = paired["device"]["deviceId"]
    headers = {"X-SmartCore-Device-Token": paired["deviceToken"]}
    assert client.post("/api/computer/activity/batch", json=_activity_payload(_bucket_start()), headers=headers).status_code == 200

    db = SessionLocal()
    try:
        removeDevice(db, "default", device_id)
        assert db.scalar(select(ComputerActivityBucket)) is not None
        assert db.scalar(select(ComputerDailyUsage)) is not None
    finally:
        db.close()

    assert client.post("/api/computer/activity/batch", json=_activity_payload(_bucket_start()), headers=headers).status_code == 401
