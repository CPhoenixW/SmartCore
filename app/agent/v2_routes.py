from __future__ import annotations

import copy
import re
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agent.routes import _AGENT_TOOLS, _done, _failed, requireAgentToken
from app.db.session import get_db
from app.new_core.ddl_service import create_ddl_event
from app.new_core.event_relations import (
    cancel_event,
    create_course_event,
    create_plan_event,
    query_events as query_relation_events,
    update_event as update_relation_event,
)
from app.new_core.models import EvtBase

_DEFAULT_TZ_NAME = "Asia/Shanghai"
_TIME_ONLY_RE = re.compile(r"^(?P<hour>[01]?\d|2[0-3]):(?P<minute>[0-5]\d)(?::(?P<second>[0-5]\d))?$")


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


def _normalize_query_body(body: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(body)
    time_range = body.get("timeRange") or body.get("time_range")
    if isinstance(time_range, dict):
        resolved_range = dict(time_range)
        if time_range.get("start") not in (None, ""):
            resolved_range["start"] = _resolved_iso(time_range["start"], body, "timeRange.start")
        if time_range.get("end") not in (None, ""):
            resolved_range["end"] = _resolved_iso(time_range["end"], body, "timeRange.end")
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
            properties.update(
                {
                    "date": {"type": "string", "format": "date", "description": "Single local date to query."},
                    "includeReminders": {"type": "boolean", "default": False},
                    "includeCourseTemplates": {"type": "boolean", "default": True},
                    "includeLinkedPlans": {"type": "boolean", "default": False},
                }
            )
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
    protected = [Depends(requireAgentToken)]

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

    @router.get("/tools", dependencies=protected)
    def list_tools() -> dict[str, Any]:
        timezone = ZoneInfo(_DEFAULT_TZ_NAME)
        now = datetime.now(timezone).replace(microsecond=0)
        tools = _enhanced_tools()
        return {
            "ok": True,
            "stat": "done",
            "data": {
                "version": "2026-07-09-course-reminder-v4",
                "authHeader": "X-SmartCore-Agent-Token",
                "requestContext": {"timezone": _DEFAULT_TZ_NAME, "now": now.isoformat()},
                "tools": tools,
            },
            "errors": [],
            "tools": tools,
        }

    @router.post("/db/query_events", dependencies=protected)
    def query_events(
        body: dict[str, Any] | None = None,
        db: Session = Depends(get_db),
    ) -> dict[str, Any]:
        try:
            return _done(query_relation_events(db, _normalize_query_body(body or {})))
        except (ValueError, TypeError) as exc:
            return _failed([str(exc)])

    @router.post("/db/create_event", dependencies=protected)
    def create_event(body: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
        try:
            evt_type = str(body.get("evtType") or body.get("type") or "").lower()
            if evt_type == "life":
                evt_type = "plan"
            title = str(body.get("title") or body.get("courseName") or "").strip()
            if not title:
                raise ValueError("title required")
            if evt_type == "plan":
                raw_time = body.get("stTime") or body.get("dueAt") or body.get("at")
                if raw_time in (None, ""):
                    raise ValueError("stTime required")
                return _done(
                    create_plan_event(
                        db,
                        title=title,
                        stTime=_resolved_iso(raw_time, body, "stTime"),
                        durationMin=int(body.get("durationMin") or 30),
                        desc=body.get("desc") or body.get("description"),
                        prio=body.get("prio") or body.get("priority") or "mid",
                        src="openclaw",
                    )
                )
            if evt_type == "ddl":
                raw_time = body.get("endTime") or body.get("ddlAt") or body.get("at")
                if raw_time in (None, ""):
                    raise ValueError("endTime required")
                plans = body.get("plans")
                normalized_plans = None
                if isinstance(plans, list):
                    normalized_plans = []
                    for index, plan in enumerate(plans):
                        if not isinstance(plan, dict):
                            raise ValueError(f"plans[{index}] must be an object")
                        normalized_plan = dict(plan)
                        if plan.get("stTime") not in (None, ""):
                            normalized_plan["stTime"] = _resolved_iso(plan["stTime"], body, f"plans[{index}].stTime")
                        normalized_plans.append(normalized_plan)
                return _done(
                    create_ddl_event(
                        db,
                        title=title,
                        endTime=_resolved_iso(raw_time, body, "endTime"),
                        hardDdl=bool(body.get("hardDdl", False)),
                        desc=body.get("desc") or body.get("description"),
                        prio=body.get("prio") or body.get("priority") or "high",
                        plans=normalized_plans,
                        src="openclaw",
                    )
                )
            if evt_type == "course":
                required = ("courseName", "stTime", "endTime", "stDate", "endDate", "weekDay")
                missing = [key for key in required if body.get(key) in (None, "")]
                if missing:
                    raise ValueError(f"required fields missing: {', '.join(missing)}")
                return _done(
                    create_course_event(
                        db,
                        title=title,
                        courseName=str(body["courseName"]),
                        teacher=body.get("teacher"),
                        location=body.get("location") or body.get("room"),
                        stTime=str(body["stTime"]),
                        endTime=str(body["endTime"]),
                        stDate=str(body["stDate"]),
                        endDate=str(body["endDate"]),
                        weekDay=body["weekDay"],
                        startWeek=int(body["startWeek"]) if body.get("startWeek") is not None else None,
                        endWeek=int(body["endWeek"]) if body.get("endWeek") is not None else None,
                        weekMode=str(body.get("weekMode") or "all"),
                        desc=body.get("desc") or body.get("description"),
                        prio=body.get("prio") or body.get("priority") or "mid",
                        src="openclaw",
                    )
                )
            raise ValueError("unsupported evtType")
        except (ValueError, TypeError, IntegrityError) as exc:
            db.rollback()
            return _failed([str(exc)])

    @router.post("/db/update_event", dependencies=protected)
    def update_event(body: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
        evt_id = body.get("evtId") or body.get("eventId")
        if not evt_id:
            return _failed(["evtId required"])
        try:
            base = db.get(EvtBase, str(evt_id))
            if base is None:
                raise ValueError(f"evt not found: {evt_id}")
            patch = _normalize_update_patch(body, evt_type=base.evtType)
            if not patch:
                raise ValueError("no supported update fields")
            return _done(update_relation_event(db, str(evt_id), src="openclaw", **patch))
        except (ValueError, TypeError, IntegrityError) as exc:
            db.rollback()
            return _failed([str(exc)])

    @router.post("/db/delete_event", dependencies=protected)
    def delete_event(body: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
        evt_id = body.get("evtId") or body.get("eventId")
        if not evt_id:
            return _failed(["evtId required"])
        try:
            return _done(cancel_event(db, str(evt_id), src="openclaw"))
        except (ValueError, TypeError, IntegrityError) as exc:
            db.rollback()
            return _failed([str(exc)])

    return router
