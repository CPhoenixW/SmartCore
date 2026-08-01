from __future__ import annotations

import copy
import re
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends

from app.server.agent.routes import _AGENT_TOOLS, _done, requireAgentToken
from app.server.agent.scope import require_agent_scope

_DEFAULT_TZ_NAME = "Asia/Shanghai"
_TIME_ONLY_RE = re.compile(r"^(?P<hour>[01]?\d|2[0-3]):(?P<minute>[0-5]\d)(?::(?P<second>[0-5]\d))?$")
_QUERY_FIELDS = {
    "date",
    "eventId",
    "evtId",
    "evtType",
    "evtTypes",
    "includeCourseTemplates",
    "includeLinkedPlans",
    "includePlans",
    "includeReminders",
    "keyword",
    "limit",
    "request",
    "stat",
    "stats",
    "text",
    "timeRange",
    "time_range",
    "timezone",
}


def _timezone_from_body(body: dict[str, Any]) -> ZoneInfo:
    request_context = body.get("request") if isinstance(body.get("request"), dict) else {}
    timezone_name = str(body.get("timezone") or request_context.get("timezone") or _DEFAULT_TZ_NAME).strip()
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"unsupported timezone: {timezone_name}") from exc


def _context_now(body: dict[str, Any], timezone: ZoneInfo) -> datetime:
    request_context = body.get("request") if isinstance(body.get("request"), dict) else {}
    raw = request_context.get("now") or body.get("now")
    if raw is None:
        return datetime.now(timezone)
    return _resolve_datetime(raw, body, field_name="request.now", timezone=timezone)


def _resolve_datetime(
    value: Any,
    body: dict[str, Any],
    *,
    field_name: str,
    timezone: ZoneInfo | None = None,
) -> datetime:
    tz = timezone or _timezone_from_body(body)
    if isinstance(value, (int, float)):
        seconds = float(value)
        if seconds > 10_000_000_000:
            seconds /= 1000.0
        return datetime.fromtimestamp(seconds, tz).replace(microsecond=0)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be an absolute date-time")
    text = value.strip()
    time_match = _TIME_ONLY_RE.fullmatch(text)
    if time_match:
        context_now = _context_now(body, tz)
        return datetime.combine(
            context_now.date(),
            time(
                int(time_match.group("hour")),
                int(time_match.group("minute")),
                int(time_match.group("second") or 0),
            ),
            tzinfo=tz,
        )
    normalized = text.replace(" ", "T", 1).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            parsed_date = date.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(
                f"{field_name} must be ISO 8601 with a date; relative text such as tomorrow/明天 is not accepted"
            ) from exc
        parsed = datetime.combine(parsed_date, time.min)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    return parsed.astimezone(tz).replace(microsecond=0)


def _resolved_iso(value: Any, body: dict[str, Any], field_name: str) -> str:
    return _resolve_datetime(value, body, field_name=field_name).isoformat()


def _resolved_absolute_iso(value: Any, body: dict[str, Any], field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be an absolute date-time with a UTC offset")
    normalized = value.strip().replace(" ", "T", 1).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an absolute date-time with a UTC offset") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include a UTC offset")
    return _resolve_datetime(value, body, field_name=field_name).isoformat()


def _normalize_query_body(body: dict[str, Any]) -> dict[str, Any]:
    unknown = sorted(set(body) - _QUERY_FIELDS)
    if unknown:
        hint = ""
        if {"start_time", "end_time", "filter"} & set(unknown):
            hint = "; use date or timeRange.start/timeRange.end"
        raise ValueError(f"unsupported query field(s): {', '.join(unknown)}{hint}")

    normalized = dict(body)
    time_range = body.get("timeRange") or body.get("time_range")
    if time_range is not None and not isinstance(time_range, dict):
        raise ValueError("timeRange must be an object with start/end")
    if isinstance(time_range, dict):
        unknown_range = sorted(set(time_range) - {"start", "end"})
        if unknown_range:
            raise ValueError(
                f"unsupported timeRange field(s): {', '.join(unknown_range)}; use start/end"
            )
        resolved_range = dict(time_range)
        if time_range.get("start") not in (None, ""):
            resolved_range["start"] = _resolved_iso(time_range["start"], body, "timeRange.start")
        if time_range.get("end") not in (None, ""):
            resolved_range["end"] = _resolved_iso(time_range["end"], body, "timeRange.end")
        if resolved_range.get("start") and resolved_range.get("end"):
            if datetime.fromisoformat(resolved_range["start"]) > datetime.fromisoformat(
                resolved_range["end"]
            ):
                raise ValueError("timeRange.start must be before timeRange.end")
        normalized["timeRange"] = resolved_range
        normalized.setdefault("includeCourseTemplates", False)
    if body.get("date"):
        normalized["date"] = str(body["date"])[:10]
        normalized.setdefault("includeCourseTemplates", False)
    return normalized


def _normalize_update_patch(
    body: dict[str, Any],
    *,
    evt_type: str | None = None,
) -> dict[str, Any]:
    aliases = {
        "description": "desc",
        "priority": "prio",
        "status": "stat",
        "dueAt": "stTime",
        "ddlAt": "endTime",
        "room": "location",
        "weekday": "weekDay",
        "startDate": "stDate",
        "finishDate": "endDate",
        "startTime": "stTime",
        "finishTime": "endTime",
    }
    allowed = {
        "title", "desc", "prio", "stat", "stTime", "endTime", "durationMin",
        "hardDdl", "courseName", "teacher", "location", "stDate", "endDate",
        "weekDay", "startWeek", "endWeek", "weekMode",
    }
    patch: dict[str, Any] = {}
    for key, value in body.items():
        normalized_key = aliases.get(key, key)
        if normalized_key not in allowed:
            continue
        if normalized_key in {"stTime", "endTime"} and value not in (None, "") and evt_type != "course":
            patch[normalized_key] = _resolved_iso(value, body, normalized_key)
        else:
            patch[normalized_key] = value
    return patch


def _enhanced_tools() -> list[dict[str, Any]]:
    tools = copy.deepcopy(_AGENT_TOOLS)
    tools.insert(
        0,
        {
            "name": "serverContext",
            "method": "GET",
            "path": "/agent/context",
            "riskLevel": "read",
            "confirmationRequired": False,
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    )
    for tool in tools:
        name = tool.get("name")
        schema = tool.get("inputSchema") or {}
        properties = schema.get("properties") or {}
        if name == "evtQuery":
            schema["additionalProperties"] = False
            properties.update(
                {
                    "date": {"type": "string", "format": "date", "description": "Single local date to query."},
                    "includeReminders": {"type": "boolean", "default": False},
                    "includeCourseTemplates": {"type": "boolean", "default": True},
                    "includeLinkedPlans": {"type": "boolean", "default": False},
                }
            )
            time_range = properties.get("timeRange")
            if isinstance(time_range, dict):
                time_range["additionalProperties"] = False
        if name in {"evtCreate", "evtUpdate"}:
            properties.update(
                {
                    "courseName": {"type": "string"},
                    "teacher": {"type": ["string", "null"]},
                    "location": {"type": ["string", "null"]},
                    "stDate": {"type": "string", "format": "date"},
                    "endDate": {"type": "string", "format": "date"},
                    "weekDay": {
                        "oneOf": [
                            {"type": "integer", "minimum": 1, "maximum": 7},
                            {"type": "string", "description": "Monday-Sunday, 周一-周日, or 星期一-星期日"},
                        ]
                    },
                    "startWeek": {"type": ["integer", "null"], "minimum": 1},
                    "endWeek": {"type": ["integer", "null"], "minimum": 1},
                    "weekMode": {"type": "string", "enum": ["all", "odd", "even"]},
                }
            )
            properties["plans"] = {
                "type": "array",
                "description": "DDL linked timed work blocks. Each item needs title, stTime, durationMin, and planRole.",
                "items": {"type": "object"},
            }
            properties["ddlReminders"] = {
                "type": "array",
                "description": "DDL linked one-shot reminders. Each item needs title and absolute triggerTime; do not use this for timed work blocks.",
                "items": {"type": "object"},
            }
        for field_name in ("stTime", "endTime", "dueAt", "ddlAt"):
            if field_name in properties:
                properties[field_name]["description"] = (
                    "For plan/DDL use absolute ISO 8601 with UTC offset. For course use local HH:MM. "
                    "Resolve relative phrases against /agent/context first."
                )
        properties["timezone"] = {
            "type": "string",
            "default": _DEFAULT_TZ_NAME,
            "description": "IANA timezone used for date-times without an explicit offset.",
        }
        properties["request"] = {
            "type": "object",
            "properties": {
                "timezone": {"type": "string"},
                "now": {"type": "string", "format": "date-time"},
            },
            "additionalProperties": True,
        }
    return tools


def createAgentV2Router() -> APIRouter:
    router = APIRouter(prefix="/agent", tags=["agent-v2"])
    protected = [Depends(requireAgentToken), Depends(require_agent_scope)]

    @router.get("/context", dependencies=protected)
    def server_context() -> dict[str, Any]:
        timezone = ZoneInfo(_DEFAULT_TZ_NAME)
        now = datetime.now(timezone).replace(microsecond=0)
        return _done(
            {
                "timezone": _DEFAULT_TZ_NAME,
                "now": now.isoformat(),
                "date": now.date().isoformat(),
                "weekday": now.isoweekday(),
                "weekdayPolicy": "Monday=1, Sunday=7",
                "utcOffset": now.strftime("%z")[:3] + ":" + now.strftime("%z")[3:],
                "timePolicy": {
                    "planAndDdl": "absolute ISO 8601 with timezone offset",
                    "courseClock": "HH:MM with stDate/endDate and weekDay",
                    "relativeText": "resolve in OpenClaw before calling event tools",
                },
                "relationPolicy": {
                    "course": "one course template expands to multiple plan events",
                    "plan": "every plan owns start-minus-10m and end-minus-10m reminder events",
                    "reminderVisibility": "reminders are push-only and hidden unless includeReminders=true",
                },
            }
        )

    return router
