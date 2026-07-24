from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.server.auth.security import require_authenticated_user_id
from app.server.computer import service
from app.server.db.session import get_db
from app.server.new_core.models import ComputerMonitorStatus, LifeDevice
from app.server.user_device.service import requireDevice

DEVICE_TOKEN_HEADER = "X-SmartCore-Device-Token"
ComputerState = Literal["active", "idle", "locked", "sleeping", "paused"]
router = APIRouter(prefix="/api/computer", tags=["computer-monitor"])


class ActivitySliceBody(BaseModel):
    state: ComputerState
    seconds: int = Field(ge=1, le=60)
    bundleId: str | None = Field(default=None, min_length=1, max_length=300)
    appName: str | None = Field(default=None, min_length=1, max_length=200)
    windowTitle: str | None = Field(default=None, max_length=300)
    titleRedacted: bool = False

    @model_validator(mode="after")
    def validate_context(self) -> ActivitySliceBody:
        if self.state == "active" and (not self.bundleId or not self.appName):
            raise ValueError("active slices require bundleId and appName")
        if self.state != "active" and any((self.bundleId, self.appName, self.windowTitle)):
            raise ValueError("only active slices may include application context")
        return self


class ActivityBucketBody(BaseModel):
    bucketStart: datetime
    timezone: str = Field(min_length=1, max_length=64)
    sessionId: str | None = Field(default=None, min_length=1, max_length=64)
    coveredSeconds: int = Field(ge=1, le=60)
    switchCount: int = Field(default=0, ge=0, le=1000)
    slices: list[ActivitySliceBody] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def validate_bucket(self) -> ActivityBucketBody:
        if self.bucketStart.tzinfo is None:
            raise ValueError("bucketStart must include an offset")
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA name") from exc
        if sum(item.seconds for item in self.slices) != self.coveredSeconds:
            raise ValueError("slice seconds must equal coveredSeconds")
        now = datetime.now(UTC)
        observed = self.bucketStart.astimezone(UTC)
        if observed < now - timedelta(days=90) or observed > now + timedelta(minutes=5):
            raise ValueError("bucketStart is outside the accepted window")
        return self


class ActivityBatchBody(BaseModel):
    schemaVersion: Literal[1]
    buckets: list[ActivityBucketBody] = Field(min_length=1, max_length=120)


class HeartbeatBody(BaseModel):
    currentState: ComputerState
    observedAt: datetime
    currentAppName: str | None = Field(default=None, max_length=200)
    currentWindowTitle: str | None = Field(default=None, max_length=300)
    appVersion: str = Field(min_length=1, max_length=50)
    osVersion: str = Field(min_length=1, max_length=100)
    accessibilityGranted: bool
    paused: bool
    queueDepth: int = Field(ge=0, le=1_000_000)

    @model_validator(mode="after")
    def validate_observed_at(self) -> HeartbeatBody:
        if self.observedAt.tzinfo is None:
            raise ValueError("observedAt must include an offset")
        return self


def _computer_device(
    db: Session = Depends(get_db),
    token: str | None = Header(default=None, alias=DEVICE_TOKEN_HEADER),
) -> LifeDevice:
    device = requireDevice(db, token)
    if device.deviceKind != "computer":
        raise HTTPException(status_code=403, detail="computer device credential required")
    return device


def _owned_computer(db: Session, user_id: str, device_id: str) -> LifeDevice:
    device = db.get(LifeDevice, device_id)
    if device is None or device.userId != user_id or device.deviceKind != "computer" or device.stat != "active":
        raise HTTPException(status_code=404, detail="computer device not found")
    return device


@router.post("/activity/batch")
def activity_batch(
    body: ActivityBatchBody,
    device: LifeDevice = Depends(_computer_device),
    db: Session = Depends(get_db),
) -> dict:
    accepted = service.ingest_activity(
        db,
        device=device,
        schema_version=body.schemaVersion,
        buckets=[item.model_dump() for item in body.buckets],
    )
    return {"ok": True, "data": {"acceptedBucketStarts": accepted}}


@router.post("/heartbeat")
def heartbeat(
    body: HeartbeatBody,
    device: LifeDevice = Depends(_computer_device),
    db: Session = Depends(get_db),
) -> dict:
    return {"ok": True, "data": service.record_heartbeat(db, device=device, payload=body.model_dump())}


@router.get("/status")
def status(
    deviceId: Annotated[str, Query(min_length=1, max_length=32)],
    userId: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict:
    device = _owned_computer(db, userId, deviceId)
    return {"ok": True, "data": service.monitor_status_dict(db.get(ComputerMonitorStatus, device.deviceId))}


@router.get("/usage")
def usage(
    deviceId: Annotated[str, Query(min_length=1, max_length=32)],
    range: Literal["today", "7d", "30d"] = "today",
    timezoneName: Annotated[str, Query(alias="timezone", min_length=1, max_length=64)] = "Asia/Shanghai",
    userId: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict:
    try:
        ZoneInfo(timezoneName)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(status_code=422, detail="timezone must be a valid IANA name") from exc
    device = _owned_computer(db, userId, deviceId)
    return {"ok": True, "data": service.usage_report(db, device=device, range_key=range, timezone_name=timezoneName)}
