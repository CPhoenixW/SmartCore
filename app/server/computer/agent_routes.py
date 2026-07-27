from __future__ import annotations

from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.server.agent.routes import requireAgentToken
from app.server.agent.scope import AgentScope, require_agent_scope
from app.server.computer.insights import (
    PROMPT_VERSION,
    build_daily_context,
    build_hour_context,
    store_daily_log,
    store_hourly_analysis,
)
from app.server.db.session import get_db
from app.server.new_core.models import LifeDevice


class PlanAssessmentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evtId: str = Field(min_length=1, max_length=64)
    state: Literal["not_started", "partial", "substantially_executed", "unclear"]
    confidence: Literal["high", "medium", "low"]
    evidenceCodes: list[str] = Field(default_factory=list, max_length=10)
    note: str | None = Field(default=None, max_length=500)


class TopicBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=40)
    summary: str | None = Field(default=None, max_length=300)
    activeSeconds: int = Field(default=0, ge=0, le=86400)
    sessionIds: list[str] = Field(default_factory=list, max_length=30)
    contextIds: list[str] = Field(default_factory=list, max_length=30)


class HourlyAnalysisBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    deviceId: str = Field(min_length=1, max_length=32)
    hourStart: datetime
    status: Literal["complete", "failed"]
    title: str | None = Field(default=None, max_length=10)
    summary: str | None = Field(default=None, max_length=800)
    planAssessments: list[PlanAssessmentBody] = Field(default_factory=list, max_length=30)
    topics: list[TopicBody] = Field(default_factory=list, max_length=10)
    evidence: dict = Field(default_factory=dict)
    model: Literal["qwen3.7-plus"] | None = None
    promptVersion: Literal["computer-analysis-v1"] = PROMPT_VERSION
    errorMessage: str | None = Field(default=None, max_length=1000)


class DailyLogBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    deviceId: str = Field(min_length=1, max_length=32)
    logDate: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    status: Literal["complete", "failed"]
    title: str | None = Field(default=None, max_length=10)
    summary: str | None = Field(default=None, max_length=1200)
    topics: list[TopicBody] = Field(default_factory=list, max_length=10)
    planAssessments: list[PlanAssessmentBody] = Field(default_factory=list, max_length=30)
    reminderSummary: list[dict] = Field(default_factory=list, max_length=50)
    hourlyAnalysisIds: list[str] = Field(default_factory=list, max_length=48)
    model: Literal["qwen3.7-plus"] | None = None
    promptVersion: Literal["computer-analysis-v1"] = PROMPT_VERSION
    errorMessage: str | None = Field(default=None, max_length=1000)


def _device(db: Session, scope: AgentScope, device_id: str) -> LifeDevice:
    device = db.get(LifeDevice, device_id)
    if (
        device is None
        or device.userId != scope.userId
        or device.deviceKind != "computer"
        or device.stat != "active"
    ):
        raise HTTPException(status_code=404, detail="computer device not found")
    return device


def createComputerAgentRouter() -> APIRouter:
    router = APIRouter(prefix="/agent/computer", tags=["agent-computer"])
    protected = [Depends(requireAgentToken), Depends(require_agent_scope)]

    @router.get("/hourly-context", dependencies=protected)
    def hourly_context(
        deviceId: str = Query(min_length=1, max_length=32),
        hourStart: datetime = Query(),
        timezone: str = Query(default="Asia/Shanghai", max_length=64),
        db: Session = Depends(get_db),
        scope: AgentScope = Depends(require_agent_scope),
    ) -> dict:
        try:
            ZoneInfo(timezone)
        except ZoneInfoNotFoundError as exc:
            raise HTTPException(status_code=422, detail="timezone must be a valid IANA name") from exc
        return {
            "ok": True,
            "data": build_hour_context(
                db,
                device=_device(db, scope, deviceId),
                hour_start=hourStart,
                timezone_name=timezone,
            ),
        }

    @router.post("/hourly-analysis", dependencies=protected)
    def hourly_analysis(
        body: HourlyAnalysisBody,
        db: Session = Depends(get_db),
        scope: AgentScope = Depends(require_agent_scope),
    ) -> dict:
        _device(db, scope, body.deviceId)
        try:
            return {
                "ok": True,
                "data": store_hourly_analysis(
                    db, user_id=scope.userId, payload=body.model_dump(mode="json")
                ),
            }
        except ValueError as exc:
            db.rollback()
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/daily-context", dependencies=protected)
    def daily_context(
        deviceId: str = Query(min_length=1, max_length=32),
        date: str = Query(pattern=r"^\d{4}-\d{2}-\d{2}$"),
        db: Session = Depends(get_db),
        scope: AgentScope = Depends(require_agent_scope),
    ) -> dict:
        return {
            "ok": True,
            "data": build_daily_context(db, device=_device(db, scope, deviceId), log_date=date),
        }

    @router.post("/daily-log", dependencies=protected)
    def daily_log(
        body: DailyLogBody,
        db: Session = Depends(get_db),
        scope: AgentScope = Depends(require_agent_scope),
    ) -> dict:
        _device(db, scope, body.deviceId)
        try:
            return {
                "ok": True,
                "data": store_daily_log(
                    db, user_id=scope.userId, payload=body.model_dump(mode="json")
                ),
            }
        except ValueError as exc:
            db.rollback()
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return router
