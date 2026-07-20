from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.security import require_authenticated_user_id
from app.db.session import get_db
from app.weather.service import get_weather

router = APIRouter(prefix="/api/weather", tags=["weather"])


@router.get("")
def weather(
    _user_id: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict:
    return {"ok": True, "data": get_weather(db)}
