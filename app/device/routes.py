from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.session import get_db
from app.device import service
from app.screen.manager import screenManager

DEVICE_TOKEN_HEADER = "X-SmartCore-Device-Token"
_DEFAULT_TZ = ZoneInfo("Asia/Shanghai")
_ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

router = APIRouter(tags=["device-v2"])


class DeviceHeartbeatBody(BaseModel):
    devId: str = Field(default="pi", min_length=1, max_length=50)
    currentTime: str
    present: bool
    person: dict[str, Any] | None = None
    persons: list[dict[str, Any]] = Field(default_factory=list)
    stateConfidence: float = Field(ge=0.0, le=1.0)
    state: Literal["working", "away", "offline", "unknown"] | None = None
    meta: dict[str, Any] | None = None


class PhotoRequestBody(BaseModel):
    reason: str | None = None
    ttlSeconds: int | None = Field(default=None, ge=30, le=3600)


class PhotoFailureBody(BaseModel):
    devId: str = Field(min_length=1, max_length=50)
    error: str = Field(min_length=1, max_length=1000)


def require_device_token(
    settings: Settings = Depends(get_settings),
    token: str | None = Header(default=None, alias=DEVICE_TOKEN_HEADER),
) -> None:
    expected = settings.device_api_token
    if not expected:
        return
    if token != expected:
        raise HTTPException(status_code=401, detail="invalid or missing device token")


def _ok(data: Any) -> dict[str, Any]:
    return {"ok": True, "data": data}


def _bad_request(exc: ValueError) -> HTTPException:
    message = str(exc)
    status = 404 if "not found" in message else 400
    return HTTPException(status_code=status, detail=message)


def _safe_component(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    if not cleaned:
        raise ValueError("invalid device id")
    return cleaned[:80]


def _date_bucket(captured_at: str) -> str:
    text = captured_at.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_DEFAULT_TZ)
    return parsed.astimezone(_DEFAULT_TZ).date().isoformat()


def _parse_recognition(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="recognition must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="recognition must be a JSON object")
    return parsed


@router.post("/dev/heartbeat", dependencies=[Depends(require_device_token)])
async def device_heartbeat(
    body: DeviceHeartbeatBody,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    persons = list(body.persons)
    if body.person is not None and not persons:
        persons = [body.person]
    try:
        state = service.record_heartbeat(
            db,
            device_id=body.devId,
            current_time=body.currentTime,
            present=body.present,
            persons=persons,
            state_confidence=body.stateConfidence,
            state=body.state,
            extra_meta=body.meta,
        )
        photo_request = service.next_pending_photo_request(db, device_id=body.devId)
    except ValueError as exc:
        raise _bad_request(exc) from exc

    await screenManager.broadcast(
        {
            "kind": "devState",
            "devId": body.devId,
            "deviceId": body.devId,
            "state": state["state"],
            "confidence": state["confidence"],
            "seenAt": state["seenAt"],
            "present": body.present,
            "persons": persons,
            "meta": state["meta"],
        }
    )
    return _ok(
        {
            "accepted": True,
            "serverTime": datetime.now(_DEFAULT_TZ).isoformat(),
            "nextHeartbeatSeconds": settings.device_heartbeat_interval_seconds,
            "state": state,
            "photoRequest": photo_request,
        }
    )


@router.get("/dev/photo/request", dependencies=[Depends(require_device_token)])
def poll_photo_request(
    devId: str = Query(min_length=1, max_length=50),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return _ok(service.next_pending_photo_request(db, device_id=devId))


@router.post("/dev/photo/{request_id}", dependencies=[Depends(require_device_token)])
async def upload_requested_photo(
    request_id: str,
    devId: str = Form(...),
    capturedAt: str = Form(...),
    recognition: str | None = Form(default=None),
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    try:
        request_row = service.get_photo_request(db, request_id)
        if request_row.deviceId != devId:
            raise ValueError("photo request does not belong to this device")
        if request_row.stat != "pending":
            raise ValueError(f"photo request is not pending: {request_row.stat}")
        date_bucket = _date_bucket(capturedAt)
        safe_device_id = _safe_component(devId)
    except ValueError as exc:
        raise _bad_request(exc) from exc

    mime_type = (image.content_type or "").lower()
    extension = _ALLOWED_IMAGE_TYPES.get(mime_type)
    if extension is None:
        raise HTTPException(status_code=415, detail="image must be JPEG, PNG, or WebP")

    content = await image.read(settings.device_photo_max_bytes + 1)
    if len(content) > settings.device_photo_max_bytes:
        raise HTTPException(status_code=413, detail="image exceeds configured size limit")
    if not content:
        raise HTTPException(status_code=400, detail="image is empty")

    recognition_data = _parse_recognition(recognition)
    destination_dir = settings.device_photo_path / safe_device_id / date_bucket
    destination = destination_dir / f"{request_id}{extension}"
    await asyncio.to_thread(destination_dir.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread(destination.write_bytes, content)

    try:
        result = service.complete_photo_request(
            db,
            request_id=request_id,
            device_id=devId,
            captured_at=capturedAt,
            image_path=str(destination),
            mime_type=mime_type,
            image_size=len(content),
            recognition=recognition_data,
        )
    except ValueError as exc:
        await asyncio.to_thread(destination.unlink, missing_ok=True)
        raise _bad_request(exc) from exc
    return _ok(result)


@router.post("/dev/photo/{request_id}/failed", dependencies=[Depends(require_device_token)])
def report_photo_failure(
    request_id: str,
    body: PhotoFailureBody,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return _ok(
            service.fail_photo_request(
                db,
                request_id=request_id,
                device_id=body.devId,
                error_message=body.error,
            )
        )
    except ValueError as exc:
        raise _bad_request(exc) from exc


@router.post("/api/device/{device_id}/photoRequest")
def create_server_photo_request(
    device_id: str,
    body: PhotoRequestBody,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    try:
        return _ok(
            service.create_photo_request(
                db,
                device_id=device_id,
                reason=body.reason,
                ttl_seconds=body.ttlSeconds or settings.device_photo_request_ttl_seconds,
            )
        )
    except ValueError as exc:
        raise _bad_request(exc) from exc


@router.get("/api/device/photoRequest/{request_id}")
def read_server_photo_request(
    request_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return _ok(service.photo_request_dict(service.get_photo_request(db, request_id)))
    except ValueError as exc:
        raise _bad_request(exc) from exc


@router.get("/api/device/{device_id}/photoRequests")
def list_server_photo_requests(
    device_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return _ok(service.list_photo_requests(db, device_id=device_id, limit=limit))


@router.get("/api/device/photoRequest/{request_id}/image")
def download_requested_photo(
    request_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    try:
        row = service.get_photo_request(db, request_id)
    except ValueError as exc:
        raise _bad_request(exc) from exc
    if row.stat != "uploaded" or not row.imagePath:
        raise HTTPException(status_code=409, detail="photo is not available")
    root = settings.device_photo_path.resolve()
    path = Path(row.imagePath).resolve()
    if not path.is_relative_to(root):
        raise HTTPException(status_code=403, detail="photo path is outside configured storage")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="photo file is missing")
    return FileResponse(path, media_type=row.mimeType or "application/octet-stream", filename=path.name)
