from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.server.device.compatibility import (
    DeviceOwnershipConflict,
    migrate_device_compatibility,
)
from app.server.new_core import crud
from app.server.new_core.models import AppUser, Device, DeviceStateLog, LifeDevice

pytestmark = pytest.mark.unit


def test_device_compatibility_backfill_is_additive_and_idempotent(db_session) -> None:
    db_session.add_all(
        [
            AppUser(userId="owner", loginName="owner", displayName="Owner"),
            Device(
                deviceId="legacy-pi",
                userId="owner",
                deviceName="Legacy Pi",
                deviceKind="pi",
            ),
            LifeDevice(
                deviceId="new-screen",
                userId="owner",
                deviceName="New screen",
                deviceKind="screen",
            ),
            LifeDevice(
                deviceId="computer-only",
                userId="owner",
                deviceName="Computer",
                deviceKind="computer",
            ),
        ]
    )
    db_session.commit()

    assert migrate_device_compatibility(db_session) == {
        "createdLifeDevices": 1,
        "createdLegacyMirrors": 1,
    }
    assert db_session.get(LifeDevice, "legacy-pi").userId == "owner"
    assert db_session.get(Device, "new-screen").userId == "owner"
    assert db_session.get(Device, "computer-only") is None
    assert migrate_device_compatibility(db_session) == {
        "createdLifeDevices": 0,
        "createdLegacyMirrors": 0,
    }


def test_device_compatibility_rejects_owner_conflicts(db_session) -> None:
    db_session.add_all(
        [
            AppUser(userId="first", loginName="first", displayName="First"),
            AppUser(userId="second", loginName="second", displayName="Second"),
            Device(
                deviceId="conflict",
                userId="first",
                deviceName="Legacy",
                deviceKind="pi",
            ),
            LifeDevice(
                deviceId="conflict",
                userId="second",
                deviceName="Life",
                deviceKind="pi",
            ),
        ]
    )
    db_session.commit()

    with pytest.raises(DeviceOwnershipConflict, match="device owner conflict"):
        migrate_device_compatibility(db_session)


def test_pi_mirrors_support_the_historical_device_kind_constraint(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy-device.sqlite'}")
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE device (
                        deviceId VARCHAR(50) PRIMARY KEY,
                        userId VARCHAR(32) NOT NULL,
                        deviceName VARCHAR(100) NOT NULL,
                        deviceKind VARCHAR(30) NOT NULL,
                        isActive INTEGER NOT NULL DEFAULT 1,
                        registeredAt VARCHAR(64) NOT NULL,
                        CHECK (deviceKind IN ('screen', 'browser', 'mobile', 'bot', 'server'))
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE lifeDevice (
                        deviceId VARCHAR(32) PRIMARY KEY,
                        userId VARCHAR(32) NOT NULL,
                        deviceName VARCHAR(100) NOT NULL,
                        deviceKind VARCHAR(30) NOT NULL,
                        stat VARCHAR(20) NOT NULL DEFAULT 'active',
                        lastSeenAt VARCHAR(64),
                        createdAt VARCHAR(64) NOT NULL,
                        updatedAt VARCHAR(64) NOT NULL
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO device (
                        deviceId, userId, deviceName, deviceKind, isActive, registeredAt
                    ) VALUES (
                        'existing-pi', 'owner', 'Old Pi', 'screen', 1,
                        '2026-08-01T00:00:00+08:00'
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO lifeDevice (
                        deviceId, userId, deviceName, deviceKind, stat, createdAt, updatedAt
                    ) VALUES
                        (
                            'existing-pi', 'owner', 'Existing Pi', 'pi', 'active',
                            '2026-08-01T00:00:00+08:00', '2026-08-01T00:00:00+08:00'
                        ),
                        (
                            'new-pi', 'owner', 'New Pi', 'pi', 'active',
                            '2026-08-01T00:00:00+08:00', '2026-08-01T00:00:00+08:00'
                        )
                    """
                )
            )

        with Session(engine) as session:
            assert migrate_device_compatibility(session) == {
                "createdLifeDevices": 0,
                "createdLegacyMirrors": 1,
            }
            assert session.get(Device, "existing-pi").deviceKind == "server"
            assert session.get(Device, "new-pi").deviceKind == "server"
            assert migrate_device_compatibility(session) == {
                "createdLifeDevices": 0,
                "createdLegacyMirrors": 0,
            }
    finally:
        engine.dispose()


def test_legacy_state_write_requires_authoritative_life_device(db_session) -> None:
    db_session.add(AppUser(userId="owner", loginName="owner", displayName="Owner"))
    db_session.commit()

    with pytest.raises(ValueError, match="lifeDevice not found"):
        crud.upsertDevState(db_session, devId="unknown-pi", state="working")

    assert db_session.get(Device, "unknown-pi") is None
    assert db_session.query(DeviceStateLog).count() == 0


def test_legacy_state_write_creates_owner_preserving_mirror(db_session) -> None:
    db_session.add_all(
        [
            AppUser(userId="owner", loginName="owner", displayName="Owner"),
            LifeDevice(
                deviceId="paired-pi",
                userId="owner",
                deviceName="Paired Pi",
                deviceKind="pi",
            ),
        ]
    )
    db_session.commit()

    state = crud.upsertDevState(db_session, devId="paired-pi", state="working")

    assert state["deviceId"] == "paired-pi"
    assert state["state"] == "working"
    assert db_session.get(Device, "paired-pi").userId == "owner"
    assert db_session.query(DeviceStateLog).filter_by(deviceId="paired-pi").count() == 1
