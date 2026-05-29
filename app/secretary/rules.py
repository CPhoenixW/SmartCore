from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from zoneinfo import ZoneInfo

DEFAULT_TZ = ZoneInfo("Asia/Shanghai")


@dataclass
class PlanItem:
    kind: str
    title: str
    time_label: str | None = None
    location: str | None = None
    notes: str | None = None
    ref_id: int | None = None


@dataclass
class DayPlan:
    target_date: date
    courses: list[PlanItem] = field(default_factory=list)
    assignments: list[PlanItem] = field(default_factory=list)
    life_events: list[PlanItem] = field(default_factory=list)
    unscheduled: list[PlanItem] = field(default_factory=list)


def format_datetime(dt: datetime | None, tz: ZoneInfo = DEFAULT_TZ) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(tz).strftime("%H:%M")
