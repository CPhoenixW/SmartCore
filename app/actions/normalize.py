from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any

from app.operations.parser import ParsedOperation
from app.secretary.rules import DEFAULT_TZ


def action_from_parsed(
    parsed: ParsedOperation,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    payload = parsed.payload
    if not isinstance(payload.get("action"), str):
        raise ValueError("parsed operation must use action protocol")

    action = dict(payload)
    action.setdefault("source", parsed.source)
    action.setdefault("raw_text", parsed.raw_text)
    action.setdefault("confidence", parsed.confidence)
    action.setdefault("needs_confirmation", parsed.needs_confirmation)
    if now is not None and "request" not in action:
        action["request"] = {
            "timezone": "Asia/Shanghai",
            "now": now.isoformat(),
        }
    return ensure_default_query_time_range(action, now)


def ensure_default_query_time_range(
    action: dict[str, Any],
    now: datetime | None,
) -> dict[str, Any]:
    if now is None or action.get("action") != "query_event":
        return action

    payload = action.get("payload")
    if not isinstance(payload, dict):
        return action
    filter_payload = payload.get("filter")
    if not isinstance(filter_payload, dict):
        filter_payload = {}

    new_filter = dict(filter_payload)
    new_filter.setdefault("event_type", "all")
    new_filter.setdefault("status", ["pending", "active"])
    new_filter.setdefault("limit", 50)
    if new_filter.get("time_range"):
        new_payload = dict(payload)
        new_payload["filter"] = new_filter
        enriched = dict(action)
        enriched["payload"] = new_payload
        return enriched

    time_range = _infer_query_time_range(str(action.get("raw_text") or ""), now)
    if not time_range:
        new_payload = dict(payload)
        new_payload["filter"] = new_filter
        enriched = dict(action)
        enriched["payload"] = new_payload
        return enriched

    new_filter["time_range"] = time_range
    new_payload = dict(payload)
    new_payload["filter"] = new_filter
    enriched = dict(action)
    enriched["payload"] = new_payload
    return enriched


def _infer_query_time_range(raw_text: str, now: datetime) -> dict[str, str] | None:
    local_now = now
    if local_now.tzinfo is None:
        local_now = local_now.replace(tzinfo=DEFAULT_TZ)
    else:
        local_now = local_now.astimezone(DEFAULT_TZ)
    today = local_now.date()

    if any(keyword in raw_text for keyword in ("今晚", "今夜")):
        start = datetime.combine(today, time(18, 0), tzinfo=local_now.tzinfo)
        end = datetime.combine(
            today + timedelta(days=1),
            time(0, 0),
            tzinfo=local_now.tzinfo,
        )
    elif any(keyword in raw_text for keyword in ("今早", "早上", "上午")):
        start = datetime.combine(today, time(6, 0), tzinfo=local_now.tzinfo)
        end = datetime.combine(today, time(12, 0), tzinfo=local_now.tzinfo)
    elif "中午" in raw_text:
        start = datetime.combine(today, time(11, 0), tzinfo=local_now.tzinfo)
        end = datetime.combine(today, time(14, 0), tzinfo=local_now.tzinfo)
    elif "下午" in raw_text:
        start = datetime.combine(today, time(12, 0), tzinfo=local_now.tzinfo)
        end = datetime.combine(today, time(18, 0), tzinfo=local_now.tzinfo)
    elif "明早" in raw_text:
        tomorrow = today + timedelta(days=1)
        start = datetime.combine(tomorrow, time(6, 0), tzinfo=local_now.tzinfo)
        end = datetime.combine(tomorrow, time(12, 0), tzinfo=local_now.tzinfo)
    elif any(keyword in raw_text for keyword in ("明天", "明日")):
        tomorrow = today + timedelta(days=1)
        start = datetime.combine(tomorrow, time(0, 0), tzinfo=local_now.tzinfo)
        end = datetime.combine(
            tomorrow + timedelta(days=1),
            time(0, 0),
            tzinfo=local_now.tzinfo,
        )
    elif any(keyword in raw_text for keyword in ("今天", "今日", "今儿")):
        start = datetime.combine(today, time(0, 0), tzinfo=local_now.tzinfo)
        end = datetime.combine(
            today + timedelta(days=1),
            time(0, 0),
            tzinfo=local_now.tzinfo,
        )
    else:
        return None

    return {"start": start.isoformat(), "end": end.isoformat()}
