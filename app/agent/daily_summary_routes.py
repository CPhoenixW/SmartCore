from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agent.routes import _done, _failed, requireAgentToken
from app.agent.scope import AgentScope, require_agent_scope
from app.db.session import get_db
from app.new_core.daily_summary_service import (
    complete_event_with_summary,
    store_daily_summary,
)


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

    @router.post("/daily-summary", dependencies=protected)
    def save_daily_summary(
        body: DailySummaryWriteBody,
        db: Session = Depends(get_db),
        scope: AgentScope = Depends(require_agent_scope),
    ) -> dict:
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
