from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.server.agent.routes import requireAgentToken
from app.server.agent.scope import AgentScope, require_agent_scope
from app.server.computer.contracts import (
    DailyLogBody,
    HourlyAnalysisBody,
    WorkBlockAnalysisBody,
)
from app.server.computer.insights import (
    build_daily_context,
    build_hour_context,
    store_daily_log,
    store_hourly_analysis,
)
from app.server.computer.work_blocks import (
    build_work_block_context,
    store_work_block_analysis,
)
from app.server.db.session import get_db
from app.server.new_core.models import LifeDevice


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
            raise HTTPException(
                status_code=422, detail="timezone must be a valid IANA name"
            ) from exc
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

    @router.get("/work-block-context", dependencies=protected)
    def work_block_context(
        runId: str = Query(min_length=1, max_length=32),
        db: Session = Depends(get_db),
        scope: AgentScope = Depends(require_agent_scope),
    ) -> dict:
        from app.server.new_core.models import ComputerWorkBlockAnalysisRun

        run = db.get(ComputerWorkBlockAnalysisRun, runId)
        if run is None or run.userId != scope.userId:
            raise HTTPException(status_code=404, detail="work block analysis run not found")
        try:
            return {
                "ok": True,
                "data": build_work_block_context(
                    db, device=_device(db, scope, run.deviceId), run=run
                ),
            }
        except ValueError as exc:
            db.rollback()
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/work-block-analysis", dependencies=protected)
    def work_block_analysis(
        body: WorkBlockAnalysisBody,
        db: Session = Depends(get_db),
        scope: AgentScope = Depends(require_agent_scope),
    ) -> dict:
        from app.server.new_core.models import ComputerWorkBlockAnalysisRun

        run = db.get(ComputerWorkBlockAnalysisRun, body.runId)
        if run is None or run.userId != scope.userId:
            raise HTTPException(status_code=404, detail="work block analysis run not found")
        try:
            return {
                "ok": True,
                "data": store_work_block_analysis(
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
