from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.server.db.session import SessionLocal
from app.server.new_core.models import Device, LifeDevice, nowIso


class DeviceOwnershipConflict(RuntimeError):
    pass


def _legacy_kind(kind: str) -> str:
    if kind in {"screen", "browser", "mobile", "bot", "server", "pi"}:
        return kind
    if kind == "feishuBot":
        return "bot"
    return "browser"


def ensure_legacy_device(db: Session, device_id: str) -> Device:
    """Return the legacy FK mirror for an authoritative lifeDevice."""
    life = db.get(LifeDevice, device_id)
    if life is None:
        raise ValueError(f"lifeDevice not found: {device_id}")
    legacy = db.get(Device, device_id)
    if legacy is not None:
        if legacy.userId != life.userId:
            raise DeviceOwnershipConflict(
                f"device owner conflict for {device_id}: "
                f"lifeDevice={life.userId}, device={legacy.userId}"
            )
        return legacy
    legacy = Device(
        deviceId=life.deviceId,
        userId=life.userId,
        deviceName=life.deviceName,
        deviceKind=_legacy_kind(life.deviceKind),
        isActive=life.stat == "active",
        registeredAt=life.createdAt or nowIso(),
    )
    db.add(legacy)
    db.flush()
    return legacy


def migrate_device_compatibility(db: Session) -> dict[str, int]:
    """Backfill both sides without merging or deleting compatibility records."""
    created_life = 0
    created_legacy = 0
    legacy_rows = list(db.scalars(select(Device).order_by(Device.deviceId)))
    for legacy in legacy_rows:
        life = db.get(LifeDevice, legacy.deviceId)
        if life is None:
            db.add(
                LifeDevice(
                    deviceId=legacy.deviceId,
                    userId=legacy.userId,
                    deviceName=legacy.deviceName,
                    deviceKind=legacy.deviceKind,
                    stat="active" if legacy.isActive else "disabled",
                    createdAt=legacy.registeredAt,
                    updatedAt=legacy.registeredAt,
                )
            )
            db.flush()
            created_life += 1
        elif life.userId != legacy.userId:
            raise DeviceOwnershipConflict(
                f"device owner conflict for {legacy.deviceId}: "
                f"lifeDevice={life.userId}, device={legacy.userId}"
            )

    life_rows = list(db.scalars(select(LifeDevice).order_by(LifeDevice.deviceId)))
    for life in life_rows:
        # Computer activity already references lifeDevice and does not use legacy
        # state/photo foreign keys.
        if life.deviceKind == "computer":
            continue
        existing_legacy = db.get(Device, life.deviceId)
        if existing_legacy is None:
            legacy = ensure_legacy_device(db, life.deviceId)
            created_legacy += 1
        else:
            legacy = ensure_legacy_device(db, life.deviceId)
        legacy.deviceName = life.deviceName
        legacy.deviceKind = _legacy_kind(life.deviceKind)
        legacy.isActive = life.stat == "active"
    db.commit()
    return {"createdLifeDevices": created_life, "createdLegacyMirrors": created_legacy}


def migrate_device_compatibility_on_startup() -> None:
    db = SessionLocal()
    try:
        migrate_device_compatibility(db)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
