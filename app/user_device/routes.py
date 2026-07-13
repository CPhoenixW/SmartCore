from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import require_authenticated_user_id
from app.db.session import get_db
from app.new_core.models import DeviceDispatch, DeviceReceipt, LifeDevice, nowIso
from app.user_device.service import (
    activatePair,
    claimPair,
    confirmPair,
    deviceDict,
    pairDict,
    pendingDispatches,
    queueDispatch,
    readClaimedPair,
    requireDevice,
    startPair,
)

DEVICE_TOKEN_HEADER = "X-SmartCore-Device-Token"
router = APIRouter(prefix="/api/device", tags=["user-device"])


class StartPairBody(BaseModel):
    deviceName: str = Field(min_length=1, max_length=100)
    deviceKind: str = Field(min_length=2, max_length=30)


class ClaimPairBody(BaseModel):
    claimCode: str = Field(min_length=8, max_length=100)
    deviceName: str | None = Field(default=None, max_length=100)


class ActivatePairBody(BaseModel):
    claimCode: str = Field(min_length=8, max_length=100)


class DispatchBody(BaseModel):
    deviceId: str
    kind: str = Field(min_length=1, max_length=50)
    payload: dict[str, Any] = Field(default_factory=dict)


class ReceiptBody(BaseModel):
    dispatchId: str
    result: str = Field(min_length=1, max_length=30)
    detail: dict[str, Any] | None = None


def _ok(data: Any) -> dict[str, Any]:
    return {"ok": True, "data": data}


def _device_from_token(db: Session = Depends(get_db), token: str | None = Header(default=None, alias=DEVICE_TOKEN_HEADER)) -> LifeDevice:
    return requireDevice(db, token)


@router.get("")
def listDevices(userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = list(db.scalars(select(LifeDevice).where(LifeDevice.userId == userId).order_by(LifeDevice.createdAt.desc())))
    return _ok([deviceDict(row) for row in rows])


@router.post("/pair/start")
def pairStart(body: StartPairBody, userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db)) -> dict[str, Any]:
    return _ok(pairDict(startPair(db, userId, body.deviceName, body.deviceKind)))


@router.get("/pair/{pairId}")
def pairRead(pairId: str, userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db)) -> dict[str, Any]:
    from app.new_core.models import DevicePair
    pair = db.get(DevicePair, pairId)
    if pair is None or pair.userId != userId:
        raise HTTPException(status_code=404, detail="pair request not found")
    return _ok(pairDict(pair))


@router.post("/pair/{pairId}/claim")
def pairClaim(pairId: str, body: ClaimPairBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    return _ok(pairDict(claimPair(db, pairId, body.claimCode, body.deviceName)))


@router.get("/pair/{pairId}/status")
def pairClaimStatus(pairId: str, claimCode: str = Query(min_length=8, max_length=100), db: Session = Depends(get_db)) -> dict[str, Any]:
    return _ok(pairDict(readClaimedPair(db, pairId, claimCode)))


@router.post("/pair/{pairId}/confirm")
def pairConfirm(pairId: str, userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db)) -> dict[str, Any]:
    return _ok(pairDict(confirmPair(db, pairId, userId)))


@router.post("/pair/{pairId}/activate")
def pairActivate(pairId: str, body: ActivatePairBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    device, token = activatePair(db, pairId, body.claimCode)
    return _ok({"device": deviceDict(device), "deviceToken": token})


@router.post("/dispatch")
def dispatch(body: DispatchBody, userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db)) -> dict[str, Any]:
    device = db.get(LifeDevice, body.deviceId)
    if device is None or device.userId != userId:
        raise HTTPException(status_code=404, detail="device not found")
    row = queueDispatch(db, device, body.kind, body.payload)
    return _ok({"dispatchId": row.dispatchId, "stat": row.stat, "userId": row.userId})


@router.get("/dispatch")
def pullDispatch(device: LifeDevice = Depends(_device_from_token), db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = pendingDispatches(db, device)
    return _ok([{"dispatchId": row.dispatchId, "kind": row.kind, "payload": row.payload, "userId": row.userId} for row in rows])


@router.post("/receipt")
def dispatchReceipt(body: ReceiptBody, device: LifeDevice = Depends(_device_from_token), db: Session = Depends(get_db)) -> dict[str, Any]:
    row = db.get(DeviceDispatch, body.dispatchId)
    if row is None or row.deviceId != device.deviceId:
        raise HTTPException(status_code=404, detail="dispatch not found")
    receipt = db.scalar(select(DeviceReceipt).where(DeviceReceipt.dispatchId == row.dispatchId))
    if receipt is None:
        receipt = DeviceReceipt(dispatchId=row.dispatchId, deviceId=device.deviceId, result=body.result, detail=body.detail)
        db.add(receipt)
    row.stat = "acknowledged"
    row.acknowledgedAt = nowIso()
    db.commit()
    return _ok({"dispatchId": row.dispatchId, "stat": row.stat})
