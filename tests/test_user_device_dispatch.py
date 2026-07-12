from __future__ import annotations

from sqlalchemy import select

from app.db.session import SessionLocal, init_db
from app.new_core import crud
from app.new_core.models import DeviceKey, LifeDevice
from app.user_device.service import (
    activatePair,
    claimPair,
    confirmPair,
    pendingDispatches,
    queueDispatch,
    requireDevice,
    startPair,
)


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
        from app.new_core.models import DeviceDispatch, DeviceReceipt

        row = db.get(DeviceDispatch, dispatch.dispatchId)
        db.add(DeviceReceipt(dispatchId=row.dispatchId, deviceId=device.deviceId, result="shown"))
        db.commit()
        assert db.scalar(select(DeviceReceipt).where(DeviceReceipt.dispatchId == row.dispatchId)) is not None
        assert db.get(LifeDevice, device.deviceId).userId == "default"
    finally:
        db.close()
