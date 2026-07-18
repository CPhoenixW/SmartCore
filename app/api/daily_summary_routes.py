from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.security import require_authenticated_user_id
from app.db.session import get_db
from app.new_core.daily_summary_service import list_daily_summaries

router = APIRouter(prefix="/api/daily-summaries", tags=["daily-summaries"])


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
