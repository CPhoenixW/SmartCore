from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.new_core.models import (
    Device,
    DeviceDispatch,
    DeviceKey,
    DevicePair,
    LifeDevice,
    LifeIdentity,
    nowIso,
)

_TZ = ZoneInfo("Asia/Shanghai")


def tokenHash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def newDeviceToken() -> str:
    return secrets.token_urlsafe(40)


def requireDevice(db: Session, token: str | None) -> LifeDevice:
    if not token:
        raise HTTPException(status_code=401, detail="device token required")
    key = db.scalar(
        select(DeviceKey).where(DeviceKey.tokenHash == tokenHash(token), DeviceKey.revokedAt.is_(None))
    )
    if key is None:
        raise HTTPException(status_code=401, detail="invalid device token")
    device = db.get(LifeDevice, key.deviceId)
    if device is None or device.stat != "active":
        raise HTTPException(status_code=403, detail="device is not active")
    key.lastUsedAt = nowIso()
    device.lastSeenAt = nowIso()
    db.commit()
    return device


def startPair(db: Session, userId: str, deviceName: str, deviceKind: str) -> DevicePair:
    if deviceKind == "feishuBot":
        pending = db.scalar(
            select(DevicePair).where(
                DevicePair.userId == userId,
                DevicePair.deviceKind == "feishuBot",
                DevicePair.stat.in_(("created", "claimed", "userConfirmed")),
                DevicePair.expiresAt > nowIso(),
            )
        )
        if pending is not None:
            raise HTTPException(status_code=409, detail="a Feishu pairing request is already pending")
    pair = DevicePair(
        userId=userId,
        deviceName=deviceName.strip() or "New device",
        deviceKind=deviceKind,
        claimCode=secrets.token_urlsafe(18),
        expiresAt=(datetime.now(_TZ) + timedelta(minutes=10)).isoformat(),
    )
    db.add(pair)
    db.commit()
    db.refresh(pair)
    return pair


def claimPair(db: Session, pairId: str, claimCode: str, deviceName: str | None = None) -> DevicePair:
    pair = db.get(DevicePair, pairId)
    if pair is None or pair.claimCode != claimCode:
        raise HTTPException(status_code=404, detail="pair request not found")
    if pair.stat not in {"created", "claimed"} or pair.expiresAt < nowIso():
        raise HTTPException(status_code=409, detail="pair request is no longer claimable")
    pair.stat = "claimed"
    if deviceName and deviceName.strip():
        pair.deviceName = deviceName.strip()
    pair.claimedAt = nowIso()
    db.commit()
    db.refresh(pair)
    return pair


def readClaimedPair(db: Session, pairId: str, claimCode: str) -> DevicePair:
    pair = db.get(DevicePair, pairId)
    if pair is None or pair.claimCode != claimCode:
        raise HTTPException(status_code=404, detail="pair request not found")
    return pair


def confirmPair(db: Session, pairId: str, userId: str) -> DevicePair:
    pair = db.get(DevicePair, pairId)
    if pair is None or pair.userId != userId:
        raise HTTPException(status_code=404, detail="pair request not found")
    if pair.stat != "claimed":
        raise HTTPException(status_code=409, detail="device has not claimed this request")
    pair.stat = "userConfirmed"
    pair.confirmedAt = nowIso()
    if pair.deviceKind == "feishuBot":
        device, _ = activatePair(db, pairId, pair.claimCode)
        identity = db.scalar(
            select(LifeIdentity)
            .where(
                LifeIdentity.userId == pair.userId,
                LifeIdentity.provider == "feishu",
                LifeIdentity.deviceId.is_(None),
            )
            .order_by(LifeIdentity.createdAt.desc())
        )
        if identity is not None:
            identity.deviceId = device.deviceId
            db.commit()
        return db.get(DevicePair, pairId) or pair
    db.commit()
    db.refresh(pair)
    return pair


def claimFeishuPair(db: Session, claimCode: str, externalId: str) -> DevicePair:
    pair = db.scalar(select(DevicePair).where(DevicePair.claimCode == claimCode))
    if pair is None or pair.deviceKind != "feishuBot":
        raise HTTPException(status_code=404, detail="feishu pairing code not found")
    existing = db.scalar(select(LifeIdentity).where(LifeIdentity.provider == "feishu", LifeIdentity.externalId == externalId))
    if existing is not None:
        raise HTTPException(status_code=409, detail="this Feishu account is already bound")
    claimed = claimPair(db, pair.pairId, claimCode, pair.deviceName)
    if existing is None:
        db.add(LifeIdentity(userId=claimed.userId, provider="feishu", externalId=externalId))
        db.commit()
        db.refresh(claimed)
    return claimed


def feishuIdentity(db: Session, externalId: str | None) -> LifeIdentity | None:
    if not externalId:
        return None
    return db.scalar(select(LifeIdentity).where(LifeIdentity.provider == "feishu", LifeIdentity.externalId == externalId, LifeIdentity.deviceId.is_not(None)))


def activatePair(db: Session, pairId: str, claimCode: str) -> tuple[LifeDevice, str]:
    pair = db.get(DevicePair, pairId)
    if pair is None or pair.claimCode != claimCode:
        raise HTTPException(status_code=404, detail="pair request not found")
    if pair.stat != "userConfirmed":
        raise HTTPException(status_code=409, detail="pair request awaits user confirmation")
    device = LifeDevice(userId=pair.userId, deviceName=pair.deviceName, deviceKind=pair.deviceKind)
    token = newDeviceToken()
    db.add(device)
    db.flush()
    db.add(
        Device(
            deviceId=device.deviceId,
            userId=device.userId,
            deviceName=device.deviceName,
            deviceKind=device.deviceKind if device.deviceKind in {"screen", "browser", "mobile", "bot", "server"} else "browser",
            isActive=True,
        )
    )
    db.add(DeviceKey(deviceId=device.deviceId, tokenHash=tokenHash(token)))
    pair.deviceId = device.deviceId
    pair.stat = "paired"
    pair.activatedAt = nowIso()
    db.commit()
    db.refresh(device)
    return device, token


def queueDispatch(db: Session, device: LifeDevice, kind: str, payload: dict) -> DeviceDispatch:
    dispatch = DeviceDispatch(deviceId=device.deviceId, userId=device.userId, kind=kind, payload=payload)
    db.add(dispatch)
    db.commit()
    db.refresh(dispatch)
    return dispatch


def pendingDispatches(db: Session, device: LifeDevice) -> list[DeviceDispatch]:
    rows = list(
        db.scalars(
            select(DeviceDispatch)
            .where(DeviceDispatch.deviceId == device.deviceId, DeviceDispatch.stat == "pending")
            .order_by(DeviceDispatch.createdAt)
        )
    )
    for row in rows:
        row.deliveredAt = nowIso()
        row.stat = "delivered"
    db.commit()
    return rows


def deviceDict(device: LifeDevice) -> dict:
    return {
        "deviceId": device.deviceId,
        "userId": device.userId,
        "deviceName": device.deviceName,
        "deviceKind": device.deviceKind,
        "stat": device.stat,
        "lastSeenAt": device.lastSeenAt,
        "createdAt": device.createdAt,
    }


def pairDict(pair: DevicePair) -> dict:
    return {
        "pairId": pair.pairId,
        "userId": pair.userId,
        "deviceId": pair.deviceId,
        "deviceName": pair.deviceName,
        "deviceKind": pair.deviceKind,
        "stat": pair.stat,
        "claimCode": pair.claimCode,
        "expiresAt": pair.expiresAt,
        "claimedAt": pair.claimedAt,
        "confirmedAt": pair.confirmedAt,
        "activatedAt": pair.activatedAt,
    }
