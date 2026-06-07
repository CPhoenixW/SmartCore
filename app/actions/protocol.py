from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.secretary.rules import DEFAULT_TZ

PUBLIC_EVENT_TYPES = frozenset({"course", "plan", "schedule", "deadline"})
LEGACY_EVENT_TYPES = frozenset({"assignment", "life_event", "course_session"})
DEFAULT_REMINDER_OFFSETS = (30, 15)
PLAN_DEFAULT_DURATION = timedelta(hours=1)

_SC_TYPE_PREFIX = "sc:"


def make_result(
    *,
    action: str,
    status: str,
    ok: bool = True,
    message_code: str = "",
    operation_id: int | None = None,
    data: dict | None = None,
    errors: list | None = None,
    model_input: dict | None = None,
    db_result: dict | None = None,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "action": action,
        "status": status,
        "message_code": message_code,
        "operation_id": operation_id,
        "data": data or {},
        "errors": errors or [],
        "debug": {
            "model_input": model_input or {},
            "db_result": db_result or {},
        },
    }


def parse_iso_datetime(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=DEFAULT_TZ)
    return dt


def normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=DEFAULT_TZ)
    return value


def format_time_label(start_at: datetime | None, end_at: datetime | None = None) -> str:
    start = normalize_datetime(start_at)
    if start is None:
        return ""
    if end_at is None:
        return start.strftime("%Y-%m-%d %H:%M")
    end = normalize_datetime(end_at)
    if end is None:
        return start.strftime("%Y-%m-%d %H:%M")
    if start.date() == end.date():
        return f"{start.strftime('%Y-%m-%d %H:%M')}-{end.strftime('%H:%M')}"
    return f"{start.strftime('%Y-%m-%d %H:%M')}-{end.strftime('%Y-%m-%d %H:%M')}"


def sc_type_tag(event_type: str) -> str:
    return f"{_SC_TYPE_PREFIX}{event_type}"


def read_sc_type(reminder_rule: str | None) -> str | None:
    if not reminder_rule or not reminder_rule.startswith(_SC_TYPE_PREFIX):
        return None
    event_type = reminder_rule.removeprefix(_SC_TYPE_PREFIX)
    if event_type in PUBLIC_EVENT_TYPES:
        return event_type
    return None


def map_legacy_event_type(event_type: str | None) -> str:
    if event_type in (None, "all"):
        return "all"
    mapping = {
        "assignment": "deadline",
        "life_event": "all",
        "course_session": "course",
    }
    if event_type in PUBLIC_EVENT_TYPES:
        return event_type
    return mapping.get(event_type, "all")


def map_status_filter(status: Any) -> set[str] | None:
    if status is None:
        return {"pending", "active"}
    if status == "open":
        return {"pending", "active"}
    if isinstance(status, str):
        return {status}
    if isinstance(status, list):
        return {str(item) for item in status}
    return {"pending", "active"}


def default_end_at(start_at: datetime, event_type: str) -> datetime | None:
    if event_type in ("plan", "course"):
        return start_at + PLAN_DEFAULT_DURATION
    return None


def default_reminder_times(start_at: datetime) -> list[datetime]:
    return [
        start_at - timedelta(minutes=offset) for offset in DEFAULT_REMINDER_OFFSETS
    ]
