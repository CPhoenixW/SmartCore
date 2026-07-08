from __future__ import annotations

import copy
import re
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agent.routes import _AGENT_TOOLS, _done, _failed, _query_events, requireAgentToken
from app.db.session import get_db
from app.new_core import crud
from app.new_core.ddl_service import create_ddl_event

_DEFAULT_TZ_NAME = "Asia/Shanghai"
_TIME_ONLY_RE = re.compile(r"^(?P<hour>[01]?\d|2[0-3]):(?P<minute>[0-5]\d)(?::(?P<second>[0-5]\d))?$")


def _timezone_from_body(body: dict[str, Any]) -> ZoneInfo:
    request_context = body.get("request") if isinstance(body.get("request"), dict) else {}
    timezone_name = str(
        body.get("timezone")
        or request_context.get("timezone")
        or _DEFAULT_TZ_NAME
    ).strip()
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
    context_now = None

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
        parsed = datetime.combine(
            context_now.date(),
            time(
                int(time_match.group("hour")),
                int(time_match.group("minute")),
                int(time_match.group("second") or 0),
            ),
            tzinfo=tz,
        )
        return parsed

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
    return normalized


def _normalize_update_patch(body: dict[str, Any]) -> dict[str, Any]:
    aliases = {
        "description": "desc",
        "priority": "prio",
        "status": "stat",
        "dueAt": "stTime",
        "ddlAt": "endTime",
        "room": "location",
    }
    allowed = {
        "title",
        "desc",
        "prio",
        "stat",
        "stTime",
        "endTime",
        "durationMin",
        "hardDdl",
        "courseName",
        "teacher",
        "location",
        "stDate",
        "endDate",
        "weekDay",
        "startWeek",
        "endWeek",
        "weekMode",
    }
    patch: dict[str, Any] = {}
    for key, value in body.items():
        normalized_key = aliases.get(key, key)
        if normalized_key not in allowed:
            continue
        if normalized_key in {"stTime", "endTime"} and value not in (None, ""):
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
        if tool.get("name") not in {"evtCreate", "evtUpdate", "evtQuery"}:
            continue
        schema = tool.get("inputSchema") or {}
        properties = schema.get("properties") or {}
        for field_name in ("stTime", "endTime", "dueAt", "ddlAt"):
            if field_name in properties:
                properties[field_name]["format"] = "date-time"
                properties[field_name]["description"] = (
                    "Absolute ISO 8601 date-time. Include a UTC offset, for example "
                    "2026-07-08T20:00:00+08:00. Resolve relative user phrases against /agent/context first."
                )
        if "timeRange" in properties:
            properties["timeRange"]["description"] = (
                "Absolute query interval resolved against /agent/context. Do not send relative phrases."
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
                "utcOffset": now.strftime("%z")[:3] + ":" + now.strftime("%z")[3:],
                "timePolicy": {
                    "storage": "absolute ISO 8601 with timezone offset",
                    "naiveDateTime": f"interpreted as {_DEFAULT_TZ_NAME}",
                    "relativeText": "resolve in OpenClaw before calling event tools",
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
                "version": "2026-07-08-time-v2",
                "authHeader": "X-SmartCore-Agent-Token",
                "requestContext": {
                    "timezone": _DEFAULT_TZ_NAME,
                    "now": now.isoformat(),
                },
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
            return _done(_query_events(db, _normalize_query_body(body or {})))
        except (ValueError, TypeError) as exc:
            return _failed([str(exc)])

    @router.post("/db/create_event", dependencies=protected)
    def create_event(body: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
        try:
            evt_type = str(body.get("evtType") or body.get("type") or "").lower()
            if evt_type == "life":
                evt_type = "plan"
            title = str(body.get("title") or "").strip()
            if not title:
                raise ValueError("title required")

            if evt_type == "plan":
                raw_time = body.get("stTime") or body.get("dueAt") or body.get("at")
                if raw_time in (None, ""):
                    raise ValueError("stTime required")
                result = crud.createPlanEvt(
                    db,
                    title=title,
                    stTime=_resolved_iso(raw_time, body, "stTime"),
                    durationMin=int(body.get("durationMin") or 30),
                    desc=body.get("desc") or body.get("description"),
                    prio=body.get("prio") or body.get("priority") or "mid",
                    src="openclaw",
                )
                return _done(result)

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
                            normalized_plan["stTime"] = _resolved_iso(
                                plan["stTime"],
                                body,
                                f"plans[{index}].stTime",
                            )
                        normalized_plans.append(normalized_plan)
                result = create_ddl_event(
                    db,
                    title=title,
                    endTime=_resolved_iso(raw_time, body, "endTime"),
                    hardDdl=bool(body.get("hardDdl", False)),
                    desc=body.get("desc") or body.get("description"),
                    prio=body.get("prio") or body.get("priority") or "high",
                    plans=normalized_plans,
                    src="openclaw",
                )
                return _done(result)

            if evt_type == "course":
                required = ("courseName", "stTime", "endTime", "stDate", "endDate", "weekDay")
                missing = [key for key in required if body.get(key) in (None, "")]
                if missing:
                    raise ValueError(f"required fields missing: {', '.join(missing)}")
                result = crud.createCourseEvt(
                    db,
                    title=title,
                    courseName=str(body["courseName"]),
                    teacher=body.get("teacher"),
                    location=body.get("location") or body.get("room"),
                    stTime=str(body["stTime"]),
                    endTime=str(body["endTime"]),
                    stDate=str(body["stDate"]),
                    endDate=str(body["endDate"]),
                    weekDay=int(body["weekDay"]),
                    startWeek=int(body["startWeek"]) if body.get("startWeek") is not None else None,
                    endWeek=int(body["endWeek"]) if body.get("endWeek") is not None else None,
                    weekMode=str(body.get("weekMode") or "all"),
                    desc=body.get("desc") or body.get("description"),
                    prio=body.get("prio") or body.get("priority") or "mid",
                    src="openclaw",
                )
                return _done(result)
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
            patch = _normalize_update_patch(body)
            if not patch:
                raise ValueError("no supported update fields")
            return _done(crud.updateEvt(db, str(evt_id), **patch))
        except (ValueError, TypeError, IntegrityError) as exc:
            db.rollback()
            return _failed([str(exc)])

    return router
