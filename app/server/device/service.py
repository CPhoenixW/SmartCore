from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.server.new_core import crud
from app.server.new_core.models import Device, DevicePhotoRequest, DeviceStateLog, nowIso

_DEFAULT_TZ = ZoneInfo("Asia/Shanghai")


def _parse_iso(value: str) -> datetime:
    text = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_DEFAULT_TZ)
    return parsed.astimezone(_DEFAULT_TZ)


def _ensure_device(db: Session, device_id: str) -> Device:
    crud.getCurrentUser(db)
    device = db.get(Device, device_id)
    if device is None:
        device = Device(
            deviceId=device_id,
            userId=crud.DEFAULT_USER_ID,
            deviceName=device_id,
            deviceKind="screen",
            isActive=True,
        )
        db.add(device)
        db.flush()
    return device


def _state_dict(row: DeviceStateLog) -> dict[str, Any]:
    return {
        "stateLogId": row.stateLogId,
        "deviceId": row.deviceId,
        "state": row.state,
        "confidence": row.confidence,
        "seenAt": row.seenAt,
        "meta": row.meta,
    }


def _latest_state_row(db: Session, device_id: str) -> DeviceStateLog | None:
    return db.scalars(
        select(DeviceStateLog)
        .where(DeviceStateLog.deviceId == device_id)
        .order_by(DeviceStateLog.seenAt.desc())
        .limit(1)
    ).first()


def _person_signature(persons: list[dict[str, Any]]) -> str:
    compact = [
        {
            "personId": item.get("personId"),
            "name": item.get("name"),
        }
        for item in persons
    ]
    return json.dumps(compact, ensure_ascii=False, sort_keys=True)


def photo_request_dict(row: DevicePhotoRequest) -> dict[str, Any]:
    return {
        "requestId": row.requestId,
        "deviceId": row.deviceId,
        "stat": row.stat,
        "reason": row.reason,
        "requestedAt": row.requestedAt,
        "expiresAt": row.expiresAt,
        "dispatchedAt": row.dispatchedAt,
        "capturedAt": row.capturedAt,
        "completedAt": row.completedAt,
        "mimeType": row.mimeType,
        "imageSize": row.imageSize,
        "recognition": row.recognition,
        "errorMessage": row.errorMessage,
        "imageAvailable": bool(row.imagePath and row.stat == "uploaded"),
        "imageUrl": (
            f"/api/device/photoRequest/{row.requestId}/image"
            if row.imagePath and row.stat == "uploaded"
            else None
        ),
    }


def record_heartbeat(
    db: Session,
    *,
    device_id: str,
    current_time: str,
    present: bool,
    persons: list[dict[str, Any]],
    state_confidence: float,
    state: str | None = None,
    extra_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reported_at = _parse_iso(current_time)
    _ensure_device(db, device_id)
    resolved_state = state or ("working" if present else "away")
    if resolved_state not in {"working", "away", "offline", "unknown"}:
        raise ValueError("state must be working, away, offline, or unknown")

    server_now = datetime.now(_DEFAULT_TZ)
    minute_bucket = server_now.strftime("%Y-%m-%dT%H:%M")
    signature = _person_signature(persons)
    meta = dict(extra_meta or {})
    meta.update(
        {
            "protocolVersion": 2,
            "reportedAt": reported_at.isoformat(),
            "receivedAt": server_now.isoformat(),
            "clockSkewSeconds": round((server_now - reported_at).total_seconds(), 3),
            "present": present,
            "persons": persons,
            "personSignature": signature,
            "logMinute": minute_bucket,
        }
    )

    latest = _latest_state_row(db, device_id)
    latest_meta = latest.meta if latest and isinstance(latest.meta, dict) else {}
    can_coalesce = bool(
        latest
        and latest_meta.get("logMinute") == minute_bucket
        and latest.state == resolved_state
        and latest_meta.get("present") == present
        and latest_meta.get("personSignature") == signature
    )
    if can_coalesce and latest is not None:
        latest.confidence = state_confidence
        latest.seenAt = server_now.isoformat()
        latest.meta = meta
        row = latest
    else:
        row = DeviceStateLog(
            deviceId=device_id,
            state=resolved_state,
            confidence=state_confidence,
            seenAt=server_now.isoformat(),
            meta=meta,
        )
        db.add(row)

    db.commit()
    db.refresh(row)
    return _state_dict(row)


def create_photo_request(
    db: Session,
    *,
    device_id: str,
    reason: str | None,
    ttl_seconds: int,
) -> dict[str, Any]:
    _ensure_device(db, device_id)
    ttl = max(30, min(int(ttl_seconds), 3600))
    requested_at = datetime.now(_DEFAULT_TZ)
    row = DevicePhotoRequest(
        deviceId=device_id,
        stat="pending",
        reason=(reason or "").strip() or None,
        requestedAt=requested_at.isoformat(),
        expiresAt=(requested_at + timedelta(seconds=ttl)).isoformat(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return photo_request_dict(row)


def get_photo_request(db: Session, request_id: str) -> DevicePhotoRequest:
    row = db.get(DevicePhotoRequest, request_id)
    if row is None:
        raise ValueError(f"photo request not found: {request_id}")
    return row


def next_pending_photo_request(
    db: Session,
    *,
    device_id: str,
) -> dict[str, Any] | None:
    now = datetime.now(_DEFAULT_TZ)
    rows = db.scalars(
        select(DevicePhotoRequest)
        .where(
            DevicePhotoRequest.deviceId == device_id,
            DevicePhotoRequest.stat == "pending",
        )
        .order_by(DevicePhotoRequest.requestedAt.asc())
    ).all()
    changed = False
    selected: DevicePhotoRequest | None = None
    for row in rows:
        try:
            expired = _parse_iso(row.expiresAt) <= now
        except ValueError:
            expired = True
        if expired:
            row.stat = "expired"
            row.completedAt = now.isoformat()
            row.errorMessage = "request expired before device upload"
            changed = True
            continue
        selected = row
        if row.dispatchedAt is None:
            row.dispatchedAt = now.isoformat()
            changed = True
        break
    if changed:
        db.commit()
    if selected is None:
        return None
    db.refresh(selected)
    return photo_request_dict(selected)


def complete_photo_request(
    db: Session,
    *,
    request_id: str,
    device_id: str,
    captured_at: str,
    image_path: str,
    mime_type: str,
    image_size: int,
    recognition: dict[str, Any] | None,
) -> dict[str, Any]:
    _parse_iso(captured_at)
    row = get_photo_request(db, request_id)
    if row.deviceId != device_id:
        raise ValueError("photo request does not belong to this device")
    if row.stat != "pending":
        raise ValueError(f"photo request is not pending: {row.stat}")
    if _parse_iso(row.expiresAt) <= datetime.now(_DEFAULT_TZ):
        row.stat = "expired"
        row.completedAt = nowIso()
        row.errorMessage = "request expired before device upload"
        db.commit()
        raise ValueError("photo request expired")
    row.stat = "uploaded"
    row.capturedAt = captured_at
    row.completedAt = nowIso()
    row.imagePath = image_path
    row.mimeType = mime_type
    row.imageSize = int(image_size)
    row.recognition = recognition
    row.errorMessage = None
    db.commit()
    db.refresh(row)
    return photo_request_dict(row)


def fail_photo_request(
    db: Session,
    *,
    request_id: str,
    device_id: str,
    error_message: str,
) -> dict[str, Any]:
    row = get_photo_request(db, request_id)
    if row.deviceId != device_id:
        raise ValueError("photo request does not belong to this device")
    if row.stat != "pending":
        raise ValueError(f"photo request is not pending: {row.stat}")
    row.stat = "failed"
    row.completedAt = nowIso()
    row.errorMessage = error_message.strip() or "device capture failed"
    db.commit()
    db.refresh(row)
    return photo_request_dict(row)


def list_photo_requests(
    db: Session,
    *,
    device_id: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(DevicePhotoRequest)
        .where(DevicePhotoRequest.deviceId == device_id)
        .order_by(DevicePhotoRequest.requestedAt.desc())
        .limit(max(1, min(int(limit), 200)))
    ).all()
    return [photo_request_dict(row) for row in rows]
