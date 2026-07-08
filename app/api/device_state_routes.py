from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.new_core.models import DeviceStateLog

router = APIRouter(prefix="/api", tags=["device-state"])


def _row_dict(row: DeviceStateLog | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        column.name: getattr(row, column.name)
        for column in row.__table__.columns
    }


@router.get("/devState/latest")
def latest_device_state(
    devId: str = Query(default="pi", min_length=1, max_length=50),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    row = db.scalar(
        select(DeviceStateLog)
        .where(DeviceStateLog.deviceId == devId)
        .order_by(DeviceStateLog.seenAt.desc())
        .limit(1)
    )
    return {"ok": True, "data": _row_dict(row)}
