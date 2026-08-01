from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.server.api import device_state_routes
from app.server.api.device_state_routes import (
    latest_device_state,
    recent_device_usage,
    today_device_usage,
)
from app.server.db.session import Base
from app.server.device import service
from app.server.device.routes import router
from app.server.new_core import (
    crud,
    models,  # noqa: F401
)
from app.server.new_core.models import DeviceStateLog, LifeDevice

pytestmark = pytest.mark.unit


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return Session(engine)


def test_latest_state_is_read_directly_from_database() -> None:
    db = _session()
    try:
        now = datetime.now(ZoneInfo("Asia/Shanghai")).replace(microsecond=0)
        db.add_all(
            [
                DeviceStateLog(
                    deviceId="pi",
                    state="away",
                    confidence=0.5,
                    seenAt=(now - timedelta(minutes=1)).isoformat(),
                    meta={"present": False},
                ),
                DeviceStateLog(
                    deviceId="pi",
                    state="working",
                    confidence=0.9,
                    seenAt=now.isoformat(),
                    meta={"present": True},
                ),
            ]
        )
        db.commit()

        payload = latest_device_state(devId="pi", db=db)
        assert payload["ok"] is True
        assert payload["data"]["state"] == "working"
        assert payload["data"]["meta"]["present"] is True
    finally:
        db.close()


def test_hourly_usage_is_aggregated_server_side() -> None:
    db = _session()
    try:
        tz = ZoneInfo("Asia/Shanghai")
        now = datetime.now(tz).replace(second=0, microsecond=0)
        start = now.replace(hour=max(0, now.hour - 1), minute=0)
        db.add_all(
            [
                DeviceStateLog(
                    deviceId="pi",
                    state="working",
                    confidence=0.8,
                    seenAt=start.isoformat(),
                    meta={"present": True},
                ),
                DeviceStateLog(
                    deviceId="pi",
                    state="away",
                    confidence=0.6,
                    seenAt=(start + timedelta(minutes=1)).isoformat(),
                    meta={"present": False},
                ),
            ]
        )
        db.commit()

        payload = today_device_usage(
            devId="pi",
            timezone="Asia/Shanghai",
            db=db,
        )
        data = payload["data"]
        assert data["sampleCount"] == 2
        assert data["hourlyMinutes"][start.hour] == 1.0
        assert data["totalMinutes"] == 1.0
        assert data["peakHour"] == start.hour
        assert data["averageConfidence"] == pytest.approx(0.7)
    finally:
        db.close()


def test_recent_usage_returns_twelve_points_across_midnight(monkeypatch) -> None:
    db = _session()
    try:
        tz = ZoneInfo("Asia/Shanghai")
        fixed_now = datetime(2026, 7, 20, 1, 30, tzinfo=tz)

        class FixedDatetime(datetime):
            @classmethod
            def now(cls, timezone=None):
                return fixed_now if timezone is None else fixed_now.astimezone(timezone)

        monkeypatch.setattr(device_state_routes, "datetime", FixedDatetime)
        working_at = datetime(2026, 7, 19, 23, 15, tzinfo=tz)
        db.add_all(
            [
                DeviceStateLog(
                    deviceId="pi",
                    state="working",
                    confidence=0.9,
                    seenAt=working_at.isoformat(),
                    meta={"present": True},
                ),
                DeviceStateLog(
                    deviceId="pi",
                    state="away",
                    confidence=0.7,
                    seenAt=(working_at + timedelta(minutes=1)).isoformat(),
                    meta={"present": False},
                ),
            ]
        )
        db.commit()

        payload = recent_device_usage(
            devId="pi",
            timezone="Asia/Shanghai",
            hours=12,
            db=db,
        )
        data = payload["data"]
        assert data["rangeHours"] == 12
        assert len(data["points"]) == 12
        assert data["points"][0]["startAt"].startswith("2026-07-19T14:00:00")
        assert data["points"][-1]["startAt"].startswith("2026-07-20T01:00:00")
        assert data["points"][9]["minutes"] == 1.0
        assert data["totalMinutes"] == 1.0
        assert data["peakStartAt"].startswith("2026-07-19T23:00:00")
    finally:
        db.close()


def test_device_router_exposes_heartbeat_and_photo_contract() -> None:
    paths = {route.path for route in router.routes}

    assert "/dev/heartbeat" in paths
    assert "/dev/photo/request" in paths
    assert "/dev/photo/{request_id}" in paths
    assert "/dev/photo/{request_id}/failed" in paths
    assert "/api/device/{device_id}/photoRequest" in paths
    assert "/api/device/photoRequest/{request_id}" in paths
    assert "/api/device/photoRequest/{request_id}/image" in paths


def test_heartbeat_and_async_photo_request_lifecycle() -> None:
    db = _session()
    try:
        crud.getCurrentUser(db)
        db.add(
            LifeDevice(
                deviceId="pi",
                userId="default",
                deviceName="Pi",
                deviceKind="pi",
            )
        )
        db.commit()
        state = service.record_heartbeat(
            db,
            device_id="pi",
            current_time="2026-07-07T21:30:10+08:00",
            present=True,
            persons=[{"name": "Phoenix", "confidence": 0.94}],
            state_confidence=0.91,
            state="working",
            extra_meta={"model": "face-v3"},
        )
        assert state["state"] == "working"
        assert state["meta"]["present"] is True
        assert state["meta"]["persons"][0]["name"] == "Phoenix"

        created = service.create_photo_request(
            db,
            device_id="pi",
            reason="integration test",
            ttl_seconds=300,
        )
        request_id = created["requestId"]
        pending = service.next_pending_photo_request(db, device_id="pi")
        assert pending is not None
        assert pending["requestId"] == request_id
        assert pending["stat"] == "pending"

        uploaded = service.complete_photo_request(
            db,
            request_id=request_id,
            device_id="pi",
            captured_at="2026-07-07T21:31:00+08:00",
            image_path="/tmp/test.jpg",
            mime_type="image/jpeg",
            image_size=128,
            recognition={"present": True},
        )
        assert uploaded["stat"] == "uploaded"
        assert uploaded["imageAvailable"] is True
        assert service.next_pending_photo_request(db, device_id="pi") is None
    finally:
        db.close()
