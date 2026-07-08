from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.device_state_routes import latest_device_state, today_device_usage
from app.db.session import Base
from app.new_core.models import AppUser, Device, DeviceStateLog


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = Session(engine)
    db.add(
        AppUser(
            userId="default",
            displayName="Default",
            language="zh",
        )
    )
    db.add(
        Device(
            deviceId="pi",
            userId="default",
            deviceName="Raspberry Pi",
            deviceKind="pi",
            isActive=True,
        )
    )
    db.commit()
    return db


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
