from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.server.agent.routes import _done, _failed, requireAgentToken
from app.server.agent.scope import AgentScope, require_agent_scope
from app.server.db.session import get_db
from app.server.new_core.daily_summary_service import (
    complete_event_with_summary,
    store_daily_summary,
)
from app.server.new_core.daily_work_context import build_daily_work_context


class DailySummaryWriteBody(BaseModel):
    reportDate: str
    content: str | None = Field(default=None, max_length=20_000)
    stat: Literal["complete", "failed"]
    errorMessage: str | None = Field(default=None, max_length=1000)


class CompleteEventBody(BaseModel):
    evtId: str = Field(min_length=1, max_length=100)
    summary: str = Field(min_length=1, max_length=4000)


def createDailySummaryAgentRouter() -> APIRouter:
    router = APIRouter(prefix="/agent", tags=["agent-daily-summary"])
    protected = [Depends(requireAgentToken), Depends(require_agent_scope)]

    @router.get("/daily-work-context", dependencies=protected)
    def daily_work_context(
        date: str = Query(pattern=r"^\d{4}-\d{2}-\d{2}$"),
        timezone: str = Query(default="Asia/Shanghai", min_length=1, max_length=64),
        db: Session = Depends(get_db),
        scope: AgentScope = Depends(require_agent_scope),
    ) -> dict:
        if scope.purpose == "daily_summary" and scope.reportDate != date:
            raise HTTPException(status_code=403, detail="daily summary scope is bound to another date")
        try:
            return _done(
                build_daily_work_context(
                    db,
                    user_id=scope.userId,
                    report_date=date,
                    timezone_name=timezone,
                )
            )
        except ValueError as exc:
            return _failed([str(exc)])

    @router.post("/daily-summary", dependencies=protected)
    def save_daily_summary(
        body: DailySummaryWriteBody,
        db: Session = Depends(get_db),
        scope: AgentScope = Depends(require_agent_scope),
    ) -> dict:
        if scope.purpose == "daily_summary" and scope.reportDate != body.reportDate:
            raise HTTPException(status_code=403, detail="daily summary scope is bound to another date")
        try:
            return _done(
                store_daily_summary(
                    db,
                    user_id=scope.userId,
                    report_date=body.reportDate,
                    content=body.content,
                    stat=body.stat,
                    error_message=body.errorMessage,
                )
            )
        except ValueError as exc:
            db.rollback()
            return _failed([str(exc)])

    @router.post("/db/complete_event", dependencies=protected)
    def complete_event(
        body: CompleteEventBody,
        db: Session = Depends(get_db),
        scope: AgentScope = Depends(require_agent_scope),
    ) -> dict:
        try:
            return _done(
                complete_event_with_summary(
                    db,
                    user_id=scope.userId,
                    event_id=body.evtId,
                    summary=body.summary,
                )
            )
        except ValueError as exc:
            db.rollback()
            return _failed([str(exc)])

    return router
