from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.server.auth.security import require_authenticated_user_id
from app.server.db.session import get_db
from app.server.new_core.daily_summary_service import (
    list_daily_summaries,
    update_daily_summary_content,
)

router = APIRouter(prefix="/api/daily-summaries", tags=["daily-summaries"])


class DailySummaryUpdateBody(BaseModel):
    content: str = Field(min_length=1, max_length=20000)
    expectedUpdatedAt: str | None = None


@router.get("")
def daily_summaries(
    date: str | None = None,
    text: str | None = Query(default=None, max_length=300),
    user_id: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return {
            "ok": True,
            "data": list_daily_summaries(
                db,
                user_id=user_id,
                report_date=date,
                text=text,
            ),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/{summary_id}")
def update_daily_summary(
    summary_id: str,
    body: DailySummaryUpdateBody,
    user_id: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return {
            "ok": True,
            "data": update_daily_summary_content(
                db,
                user_id=user_id,
                summary_id=summary_id,
                content=body.content,
                expected_updated_at=body.expectedUpdatedAt,
            ),
        }
    except ValueError as exc:
        if str(exc) == "daily summary not found":
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if str(exc) == "stale daily summary":
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
