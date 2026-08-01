from __future__ import annotations

import pytest

from app.server.device.compatibility import (
    DeviceOwnershipConflict,
    migrate_device_compatibility,
)
from app.server.new_core.models import AppUser, Device, LifeDevice

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
