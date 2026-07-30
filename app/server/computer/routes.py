from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from app.server.auth.security import require_authenticated_user_id
from app.server.computer import service
from app.server.db.session import get_db
from app.server.new_core.models import LifeDevice
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
    contextKind: Literal["application", "browser", "ide", "document"] | None = None
    domain: str | None = Field(default=None, max_length=253)
    workspace: str | None = Field(default=None, max_length=300)
    documentName: str | None = Field(default=None, max_length=300)
    titleRedacted: bool = False

    @model_validator(mode="after")
    def validate_context(self) -> ActivitySliceBody:
        if self.state == "active" and (not self.bundleId or not self.appName):
            raise ValueError("active slices require bundleId and appName")
        context_values = (
            self.bundleId,
            self.appName,
            self.windowTitle,
            self.contextKind,
            self.domain,
            self.workspace,
            self.documentName,
        )
        if self.state != "active" and any(context_values):
            raise ValueError("only active slices may include application context")
        if self.titleRedacted and any(
            (self.windowTitle, self.contextKind, self.domain, self.workspace, self.documentName)
        ):
            raise ValueError("redacted contexts may only include application identity")
        if self.domain and any(character in self.domain for character in ("/", ":", "?", "#", "@")):
            raise ValueError("domain must be a hostname without URL components")
        if any(
            value and any(character in value for character in ("/", "\\"))
            for value in (self.workspace, self.documentName)
        ):
            raise ValueError("workspace and documentName must not include a path")
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


class CodexWorkEvidenceBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    commits: list[str] = Field(default_factory=list, max_length=20)
    pullRequests: list[str] = Field(default_factory=list, max_length=20)
    tests: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("commits", "pullRequests", "tests")
    @classmethod
    def validate_evidence_items(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            item = " ".join(value.split())
            if not item or "\n" in value or "\r" in value or len(item) > 200:
                raise ValueError("evidence items must be non-empty single-line strings up to 200 characters")
            normalized.append(item)
        return normalized


class CodexWorkReportBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    sourceTaskId: str = Field(min_length=1, max_length=200)
    reportDate: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    timezone: str = Field(min_length=1, max_length=64)
    projectKey: str = Field(min_length=1, max_length=300)
    projectName: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=300)
    summary: str = Field(min_length=1, max_length=2000)
    status: Literal["completed", "partial", "in_progress"]
    startedAt: datetime | None = None
    endedAt: datetime | None = None
    evidence: CodexWorkEvidenceBody = Field(default_factory=CodexWorkEvidenceBody)

    @field_validator(
        "sourceTaskId", "timezone", "projectKey", "projectName", "title"
    )
    @classmethod
    def validate_single_line_text(cls, value: str) -> str:
        if "\n" in value or "\r" in value:
            raise ValueError("text fields must be single-line")
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("text fields must not be blank")
        return normalized

    @field_validator("reportDate")
    @classmethod
    def validate_report_date(cls, value: str) -> str:
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("reportDate must be YYYY-MM-DD") from exc
        if parsed.isoformat() != value:
            raise ValueError("reportDate must be YYYY-MM-DD")
        return value

    @field_validator("startedAt", "endedAt", mode="before")
    @classmethod
    def validate_timestamp_input(cls, value: object) -> object:
        if value is not None and not isinstance(value, str):
            raise ValueError("timestamps must be ISO-8601 strings")
        return value

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, value: str) -> str:
        if "\n" in value or "\r" in value:
            raise ValueError("summary must be one paragraph")
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("summary must not be blank")
        return normalized

    @model_validator(mode="after")
    def validate_report(self) -> CodexWorkReportBody:
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA name") from exc
        for field_name, value in (("startedAt", self.startedAt), ("endedAt", self.endedAt)):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError(f"{field_name} must include an offset")
        if self.startedAt and self.endedAt and self.endedAt < self.startedAt:
            raise ValueError("endedAt must not be earlier than startedAt")
        return self


class CodexWorkReportBatchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reports: list[CodexWorkReportBody] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_unique_reports(self) -> CodexWorkReportBatchBody:
        keys = [(item.sourceTaskId, item.reportDate) for item in self.reports]
        if len(keys) != len(set(keys)):
            raise ValueError("batch contains duplicate sourceTaskId/reportDate entries")
        return self


class HeartbeatBody(BaseModel):
    currentState: ComputerState
    observedAt: datetime
    currentAppName: str | None = Field(default=None, max_length=200)
    currentWindowTitle: str | None = Field(default=None, max_length=300)
    appVersion: str = Field(min_length=1, max_length=50)
    osVersion: str = Field(min_length=1, max_length=100)
    accessibilityGranted: bool = True
    paused: bool = False
    queueDepth: int = Field(ge=0, le=1_000_000)

    @model_validator(mode="after")
    def validate_observed_at(self) -> HeartbeatBody:
        if self.observedAt.tzinfo is None:
            raise ValueError("observedAt must include an offset")
        if self.currentState != "active" and any((self.currentAppName, self.currentWindowTitle)):
            raise ValueError("only active heartbeats may include application context")
        if self.currentWindowTitle and not self.currentAppName:
            raise ValueError("window title requires an application")
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
    if (
        device is None
        or device.userId != user_id
        or device.deviceKind != "computer"
        or device.stat != "active"
    ):
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
    return {
        "ok": True,
        "data": service.record_heartbeat(db, device=device, payload=body.model_dump()),
    }


@router.post("/codex-reports/batch")
def codex_report_batch(
    body: CodexWorkReportBatchBody,
    device: LifeDevice = Depends(_computer_device),
    db: Session = Depends(get_db),
) -> dict:
    try:
        accepted = service.upsert_codex_work_reports(
            db, device=device, reports=[item.model_dump(mode="json") for item in body.reports]
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True, "data": {"acceptedReports": accepted}}


@router.get("/codex-reports")
def codex_reports(
    dateValue: Annotated[
        str, Query(alias="date", min_length=10, max_length=10)
    ],
    userId: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict:
    try:
        report_date = date.fromisoformat(dateValue).isoformat()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="date must be YYYY-MM-DD") from exc
    items = service.list_codex_work_reports(db, user_id=userId, report_date=report_date)
    return {"ok": True, "data": {"items": items, "count": len(items)}}


@router.get("/status")
def status(
    deviceId: Annotated[str, Query(min_length=1, max_length=32)],
    userId: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict:
    device = _owned_computer(db, userId, deviceId)
    return {"ok": True, "data": service.monitor_status_with_analysis(db, device=device)}


@router.get("/usage")
def usage(
    deviceId: Annotated[str, Query(min_length=1, max_length=32)],
    range: Literal["today", "24h", "7d", "30d"] = "today",
    timezoneName: Annotated[
        str, Query(alias="timezone", min_length=1, max_length=64)
    ] = "Asia/Shanghai",
    userId: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict:
    try:
        ZoneInfo(timezoneName)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(status_code=422, detail="timezone must be a valid IANA name") from exc
    device = _owned_computer(db, userId, deviceId)
    return {
        "ok": True,
        "data": service.usage_report(
            db, device=device, range_key=range, timezone_name=timezoneName
        ),
    }


@router.get("/insights")
def insights(
    deviceId: Annotated[str, Query(min_length=1, max_length=32)],
    dateValue: Annotated[str | None, Query(alias="date")] = None,
    userId: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict:
    from app.server.computer.insights import insights_report

    try:
        log_date = (
            date.fromisoformat(dateValue).isoformat()
            if dateValue
            else datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="date must be YYYY-MM-DD") from exc
    device = _owned_computer(db, userId, deviceId)
    return {"ok": True, "data": insights_report(db, device=device, log_date=log_date)}
