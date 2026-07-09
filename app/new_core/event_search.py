from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Iterable
from zoneinfo import ZoneInfo

_DEFAULT_TZ = ZoneInfo("Asia/Shanghai")
_WEEKDAY_NAMES = {
    1: ("星期一", "周一", "monday", "mon"),
    2: ("星期二", "周二", "tuesday", "tue"),
    3: ("星期三", "周三", "wednesday", "wed"),
    4: ("星期四", "周四", "thursday", "thu"),
    5: ("星期五", "周五", "friday", "fri"),
    6: ("星期六", "周六", "saturday", "sat"),
    7: ("星期日", "周日", "星期天", "周天", "sunday", "sun"),
}


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_DEFAULT_TZ)
    return parsed.astimezone(_DEFAULT_TZ)


def _time_tokens(value: Any) -> list[str]:
    parsed = _parse_datetime(value)
    if parsed is None:
        text = str(value or "").strip().lower()
        return [text] if text else []
    weekday = parsed.isoweekday()
    return [
        parsed.isoformat().lower(),
        parsed.strftime("%Y-%m-%d").lower(),
        parsed.strftime("%Y/%m/%d").lower(),
        parsed.strftime("%m-%d").lower(),
        parsed.strftime("%H:%M").lower(),
        parsed.strftime("%H:%M:%S").lower(),
        f"{parsed.year}年{parsed.month}月{parsed.day}日",
        f"{parsed.month}月{parsed.day}日",
        f"{parsed.hour}点",
        f"{parsed.hour}点{parsed.minute}分",
        *_WEEKDAY_NAMES[weekday],
    ]


def normalize_search_query(query: str, *, now: datetime | None = None) -> str:
    text = str(query or "").strip().lower()
    if not text:
        return ""
    current = now or datetime.now(_DEFAULT_TZ)
    relative = {
        "今天": current,
        "今日": current,
        "明天": current + timedelta(days=1),
        "后天": current + timedelta(days=2),
        "昨天": current - timedelta(days=1),
    }
    for label, target in relative.items():
        text = text.replace(label, target.strftime("%Y-%m-%d"))
    text = text.replace("/", "-")
    text = re.sub(
        r"(20\d{2})年(\d{1,2})月(\d{1,2})日?",
        lambda m: f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}",
        text,
    )
    text = re.sub(
        r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b",
        lambda m: f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}",
        text,
    )
    text = re.sub(r"\b(\d{1,2})点半\b", lambda m: f"{int(m.group(1)):02d}:30", text)
    text = re.sub(
        r"\b(\d{1,2})点(?:(\d{1,2})分?)?\b",
        lambda m: f"{int(m.group(1)):02d}:{int(m.group(2) or 0):02d}",
        text,
    )
    text = re.sub(r"\s+", " ", text).strip()
    return text


def event_search_text(item: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in (
        "title",
        "desc",
        "evtType",
        "prio",
        "stat",
        "courseName",
        "teacher",
        "location",
        "occurrenceDate",
        "semesterStart",
        "stDate",
        "computedEndDate",
        "endDate",
        "remindKind",
        "planRole",
    ):
        value = item.get(key)
        if value not in (None, ""):
            parts.append(str(value).lower())
    for key in (
        "stTime",
        "endTime",
        "triggerTime",
        "occurrenceDate",
        "semesterStart",
        "stDate",
        "computedEndDate",
        "endDate",
        "createdAt",
        "updatedAt",
    ):
        parts.extend(_time_tokens(item.get(key)))
    weekday = item.get("weekDay")
    if weekday is not None:
        try:
            parts.extend(_WEEKDAY_NAMES[int(weekday)])
        except (KeyError, TypeError, ValueError):
            pass
    if item.get("durationMin") is not None:
        parts.extend(
            [
                str(item["durationMin"]),
                f"{item['durationMin']}分钟",
            ]
        )
    if item.get("startWeek") is not None:
        parts.append(f"第{item['startWeek']}周")
    if item.get("endWeek") is not None:
        parts.append(f"第{item['endWeek']}周")
    for plan in item.get("plans") or []:
        if isinstance(plan, dict):
            parts.append(event_search_text(plan))
    return " ".join(parts).lower()


def filter_events_by_text(
    items: Iterable[dict[str, Any]],
    query: str | None,
) -> list[dict[str, Any]]:
    normalized = normalize_search_query(query or "")
    if not normalized:
        return list(items)
    terms = [term for term in normalized.split(" ") if term]
    result: list[dict[str, Any]] = []
    for item in items:
        haystack = event_search_text(item)
        if all(term in haystack for term in terms):
            result.append(item)
    return result
