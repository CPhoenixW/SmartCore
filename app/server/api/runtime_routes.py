from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Query

from app.server.auth.security import require_authenticated_user_id
from app.server.config import Settings, get_settings

router = APIRouter(prefix="/api/runtime", tags=["runtime"])


def _timezone(value: str | None, settings: Settings) -> tuple[str, ZoneInfo]:
    name = (value or settings.daily_summary_timezone or "Asia/Shanghai").strip()
    try:
        return name, ZoneInfo(name)
    except ZoneInfoNotFoundError:
        fallback = settings.daily_summary_timezone or "Asia/Shanghai"
        return fallback, ZoneInfo(fallback)


@router.get("/clock")
def runtime_clock(
    timezone: str | None = Query(default=None, max_length=64),
    _user_id: str = Depends(require_authenticated_user_id),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    timezone_name, local_zone = _timezone(timezone, settings)
    now_utc = datetime.now(UTC).replace(microsecond=0)
    now_local = now_utc.astimezone(local_zone)
    offset = now_local.utcoffset()
    return {
        "ok": True,
        "data": {
            "serverNow": now_local.isoformat(),
            "utcNow": now_utc.isoformat().replace("+00:00", "Z"),
            "timezone": timezone_name,
            "offsetMinutes": int(offset.total_seconds() // 60) if offset else 0,
            "source": "server",
        },
    }
