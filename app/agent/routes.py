from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agent.scope import AgentScope, require_agent_scope
from app.config import Settings, get_settings
from app.db.session import get_db
from app.feishu.client import FeishuAPIError, FeishuClient
from app.new_core import crud
from app.new_core.models import DdlPlan, EvtBase, Idea
from app.screen.manager import screenManager

AGENT_TOKEN_HEADER = "X-SmartCore-Agent-Token"
DEVICE_TOKEN_HEADER = "X-SmartCore-Device-Token"
_DEFAULT_TZ = ZoneInfo("Asia/Shanghai")


def _schema_object(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": True,
    }
    if required:
        schema["required"] = required
    return schema


_AGENT_TOOLS: list[dict[str, Any]] = [
    {
        "name": "evtQuery",
        "method": "POST",
        "path": "/agent/db/query_events",
        "legacyPaths": ["/agent/evtQuery"],
        "riskLevel": "read",
        "confirmationRequired": False,
        "inputSchema": _schema_object(
            {
                "evtId": {"type": "string"},
                "evtType": {
                    "oneOf": [
                        {"type": "string", "enum": ["plan", "life", "ddl", "course"]},
                        {
                            "type": "array",
                            "items": {"type": "string", "enum": ["plan", "life", "ddl", "course"]},
                        },
                    ]
                },
                "stat": {
                    "oneOf": [
                        {"type": "string", "enum": ["todo", "done", "cancelled"]},
                        {
                            "type": "array",
                            "items": {"type": "string", "enum": ["todo", "done", "cancelled"]},
                        },
                    ]
                },
                "text": {"type": "string"},
                "timeRange": _schema_object(
                    {
                        "start": {"type": "string", "format": "date-time"},
                        "end": {"type": "string", "format": "date-time"},
                    }
                ),
                "includeLinkedPlans": {"type": "boolean", "default": False},
                "includePlans": {"type": "boolean", "default": True},
                "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 100},
            }
        ),
    },
    {
        "name": "evtCreate",
        "method": "POST",
        "path": "/agent/db/create_event",
        "legacyPaths": ["/agent/evtCreate"],
        "riskLevel": "write",
        "confirmationRequired": False,
        "inputSchema": _schema_object(
            {
                "evtType": {"type": "string", "enum": ["plan", "life", "ddl", "course"]},
                "title": {"type": "string", "minLength": 1},
                "desc": {"type": "string"},
                "prio": {"type": "string", "enum": ["low", "mid", "high"]},
                "stTime": {"type": "string"},
                "endTime": {"type": "string"},
                "dueAt": {"type": "string"},
                "ddlAt": {"type": "string"},
                "durationMin": {"type": "integer", "minimum": 1},
                "hardDdl": {"type": "boolean"},
            },
            ["evtType", "title"],
        ),
    },
    {
        "name": "evtUpdate",
        "method": "POST",
        "path": "/agent/db/update_event",
        "legacyPaths": ["/agent/evtUpdate"],
        "riskLevel": "write",
        "confirmationRequired": False,
        "inputSchema": _schema_object(
            {
                "evtId": {"type": "string", "minLength": 1},
                "title": {"type": "string"},
                "desc": {"type": ["string", "null"]},
                "prio": {"type": "string", "enum": ["low", "mid", "high"]},
                "stat": {"type": "string", "enum": ["todo", "done", "cancelled"]},
                "stTime": {"type": "string"},
                "endTime": {"type": "string"},
                "dueAt": {"type": "string"},
                "ddlAt": {"type": "string"},
                "durationMin": {"type": "integer", "minimum": 1},
                "hardDdl": {"type": "boolean"},
            },
            ["evtId"],
        ),
    },
    {
        "name": "evtComplete",
        "method": "POST",
        "path": "/agent/db/complete_event",
        "riskLevel": "write",
        "confirmationRequired": False,
        "description": (
            "Mark an owned event done and append a completion result or reflection "
            "to its existing description."
        ),
        "inputSchema": _schema_object(
            {
                "evtId": {"type": "string", "minLength": 1},
                "summary": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 4000,
                    "description": "What was completed, the outcome, and any reflection.",
                },
            },
            ["evtId", "summary"],
        ),
    },
    {
        "name": "evtDelete",
        "method": "POST",
        "path": "/agent/db/delete_event",
        "legacyPaths": ["/agent/evtDelete"],
        "riskLevel": "destructive",
        "confirmationRequired": False,
        "inputSchema": _schema_object({"evtId": {"type": "string", "minLength": 1}}, ["evtId"]),
    },
    {
        "name": "ideaCapture",
        "method": "POST",
        "path": "/agent/idea/capture",
        "legacyPaths": ["/agent/ideaCapture"],
        "riskLevel": "write",
        "confirmationRequired": False,
        "inputSchema": _schema_object(
            {
                "content": {"type": "string", "minLength": 1},
                "srcType": {"type": "string", "enum": ["text", "voice", "ocr"]},
                "mediaPath": {"type": ["string", "null"]},
            },
            ["content"],
        ),
    },
    {
        "name": "ideaToEvt",
        "method": "POST",
        "path": "/agent/idea/to_event",
        "legacyPaths": ["/agent/ideaToEvt"],
        "riskLevel": "write",
        "confirmationRequired": False,
        "inputSchema": _schema_object(
            {
                "ideaId": {"type": "string", "minLength": 1},
                "evtType": {"type": "string", "enum": ["plan", "life", "ddl"]},
                "title": {"type": "string"},
                "desc": {"type": "string"},
                "stTime": {"type": "string"},
                "endTime": {"type": "string"},
                "durationMin": {"type": "integer", "minimum": 1},
                "hardDdl": {"type": "boolean"},
                "prio": {"type": "string", "enum": ["low", "mid", "high"]},
            },
            ["ideaId"],
        ),
    },
    {
        "name": "sendFeishuText",
        "method": "POST",
        "path": "/agent/feedback/send_text",
        "legacyPaths": ["/agent/sendText"],
        "riskLevel": "external",
        "confirmationRequired": False,
        "inputSchema": _schema_object(
            {
                "text": {"type": "string", "minLength": 1},
                "receiveId": {"type": "string"},
                "chatId": {"type": "string"},
            },
            ["text"],
        ),
    },
    {
        "name": "sendFeishuCard",
        "method": "POST",
        "path": "/agent/feedback/send_card",
        "legacyPaths": ["/agent/sendCard"],
        "riskLevel": "external",
        "confirmationRequired": False,
        "inputSchema": _schema_object(
            {
                "card": {"type": "object"},
                "receiveId": {"type": "string"},
                "chatId": {"type": "string"},
            },
            ["card"],
        ),
    },
    {
        "name": "screenPush",
        "method": "POST",
        "path": "/agent/feedback/screen_push",
        "legacyPaths": ["/agent/screenPush"],
        "riskLevel": "external",
        "confirmationRequired": False,
        "inputSchema": _schema_object(
            {
                "evtId": {"type": "string"},
                "title": {"type": "string"},
                "content": {"type": "string"},
            }
        ),
    },
]

_feishuClient: FeishuClient | None = None


def _getFeishuClient(settings: Settings) -> FeishuClient | None:
    global _feishuClient
    if _feishuClient is not None:
        return _feishuClient
    if not settings.feishu_app_id or not settings.feishu_app_secret:
        return None
    if _feishuClient is None:
        _feishuClient = FeishuClient(settings.feishu_app_id, settings.feishu_app_secret)
    return _feishuClient


def _resolveReceiveId(body: dict[str, Any], settings: Settings) -> str | None:
    for key in ("receiveId", "receive_id", "chatId", "chat_id"):
        value = body.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return settings.feishu_default_chat_id or None


def _failed(errors: list[str]) -> dict[str, Any]:
    return {"ok": False, "stat": "failed", "data": None, "errors": errors}


def _done(data: Any) -> dict[str, Any]:
    return {"ok": True, "stat": "done", "data": data, "errors": []}


def _as_string_set(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return {value}
    if isinstance(value, list):
        return {str(item) for item in value if item is not None}
    return {str(value)}


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.combine(date.fromisoformat(text), datetime.min.time())
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_DEFAULT_TZ)
    return parsed.astimezone(_DEFAULT_TZ)


def _event_interval(event: dict[str, Any]) -> tuple[datetime | None, datetime | None]:
    evt_type = event.get("evtType")
    if evt_type == "ddl":
        instant = _parse_datetime(event.get("endTime"))
        return instant, instant
    if evt_type == "plan":
        start = _parse_datetime(event.get("stTime"))
        if start is None:
            return None, None
        return start, start + timedelta(minutes=int(event.get("durationMin") or 0))
    return None, None


def _course_in_range(event: dict[str, Any], start: datetime | None, end: datetime | None) -> bool:
    if start is None and end is None:
        return True
    try:
        course_start = date.fromisoformat(str(event.get("stDate", ""))[:10])
        course_end = date.fromisoformat(str(event.get("endDate", ""))[:10])
        weekday = int(event.get("weekDay"))
    except (TypeError, ValueError):
        return False
    left = max(course_start, start.date() if start else course_start)
    right = min(course_end, end.date() if end else course_end)
    if left > right:
        return False
    offset = (weekday - left.isoweekday()) % 7
    return left + timedelta(days=offset) <= right


def _overlaps_range(
    event: dict[str, Any], start: datetime | None, end: datetime | None
) -> bool:
    if start is None and end is None:
        return True
    if event.get("evtType") == "course":
        return _course_in_range(event, start, end)
    event_start, event_end = _event_interval(event)
    if event_start is None:
        return False
    if start is not None and event_end is not None and event_end < start:
        return False
    if end is not None and event_start > end:
        return False
    return True


def _linked_plan_map(db: Session) -> dict[str, dict[str, Any]]:
    links = db.scalars(select(DdlPlan).order_by(DdlPlan.sortOrder.asc())).all()
    return {
        link.planEvtId: {
            "ddlEvtId": link.ddlEvtId,
            "planRole": link.planRole,
            "sortOrder": link.sortOrder,
        }
        for link in links
    }


def _query_events(db: Session, body: dict[str, Any]) -> dict[str, Any]:
    events = crud.listEvt(db)
    linked = _linked_plan_map(db)
    include_linked = bool(body.get("includeLinkedPlans", body.get("include_linked_plans", False)))
    include_plans = bool(body.get("includePlans", body.get("include_plans", True)))
    evt_id = body.get("evtId") or body.get("eventId")
    evt_types = _as_string_set(body.get("evtType") or body.get("evtTypes"))
    evt_types = {"plan" if item == "life" else item for item in evt_types}
    stats = _as_string_set(body.get("stat") or body.get("stats"))
    text = str(body.get("text") or body.get("query") or "").strip().lower()
    time_range = body.get("timeRange") or body.get("time_range") or {}
    start = _parse_datetime(time_range.get("start") if isinstance(time_range, dict) else None)
    end = _parse_datetime(time_range.get("end") if isinstance(time_range, dict) else None)
    if start and end and start > end:
        raise ValueError("timeRange.start must be before timeRange.end")

    filtered: list[dict[str, Any]] = []
    for original in events:
        event = dict(original)
        link = linked.get(str(event.get("evtId")))
        if link and not include_linked:
            continue
        if link:
            event["ddlLink"] = link
        if not include_plans and event.get("evtType") == "ddl":
            event.pop("plans", None)
        if evt_id and event.get("evtId") != evt_id:
            continue
        if evt_types and event.get("evtType") not in evt_types:
            continue
        if stats and event.get("stat") not in stats:
            continue
        if text:
            haystack = " ".join(
                str(event.get(key) or "")
                for key in ("title", "desc", "courseName", "teacher", "location")
            ).lower()
            if text not in haystack:
                continue
        if not _overlaps_range(event, start, end):
            continue
        filtered.append(event)

    def sort_key(item: dict[str, Any]) -> tuple[int, str]:
        event_start, _ = _event_interval(item)
        if item.get("evtType") == "course":
            return 0, str(item.get("stDate") or "") + str(item.get("stTime") or "")
        return (0, event_start.isoformat()) if event_start else (1, str(item.get("createdAt") or ""))

    filtered.sort(key=sort_key)
    limit = int(body.get("limit") or 100)
    limit = max(1, min(limit, 500))
    result = filtered[:limit]
    return {
        "events": result,
        "count": len(result),
        "totalMatched": len(filtered),
        "truncated": len(filtered) > limit,
    }


def _run_write(db: Session, operation: Callable[[], Any]) -> dict[str, Any]:
    try:
        return _done(operation())
    except (ValueError, TypeError, IntegrityError) as exc:
        db.rollback()
        return _failed([str(exc)])


def requireAgentToken(
    settings: Settings = Depends(get_settings),
    x_smartcore_agent_token: str | None = Header(default=None, alias=AGENT_TOKEN_HEADER),
) -> None:
    expected = settings.agent_api_token
    if not expected:
        return
    if x_smartcore_agent_token != expected:
        raise HTTPException(status_code=401, detail="invalid or missing agent token")


def requireDeviceToken(
    settings: Settings = Depends(get_settings),
    x_smartcore_device_token: str | None = Header(default=None, alias=DEVICE_TOKEN_HEADER),
) -> None:
    expected = settings.device_api_token
    if not expected:
        return
    if x_smartcore_device_token != expected:
        raise HTTPException(status_code=401, detail="invalid or missing device token")


class DevStateBody(BaseModel):
    devId: str
    state: str
    confidence: float | None = None
    seenAt: str | None = None
    meta: dict | None = None


def createAgentRouter() -> APIRouter:
    router = APIRouter(prefix="/agent", tags=["agent"])
    protected = [Depends(requireAgentToken), Depends(require_agent_scope)]

    @router.get("/tools", dependencies=protected)
    def listTools() -> dict[str, Any]:
        return {
            "ok": True,
            "stat": "done",
            "data": {
                "version": "2026-07-07",
                "authHeader": AGENT_TOKEN_HEADER,
                "tools": _AGENT_TOOLS,
            },
            "errors": [],
            "tools": _AGENT_TOOLS,
        }

    @router.post("/evtQuery", dependencies=protected)
    @router.post("/db/query_events", dependencies=protected)
    def evtQuery(
        body: dict[str, Any] | None = None,
        db: Session = Depends(get_db),
    ) -> dict[str, Any]:
        try:
            return _done(_query_events(db, body or {}))
        except (ValueError, TypeError) as exc:
            return _failed([str(exc)])

    @router.post("/evtCreate", dependencies=protected)
    @router.post("/db/create_event", dependencies=protected)
    def evtCreate(body: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            evt_type = str(body.get("evtType") or body.get("type") or "").lower()
            if evt_type == "life":
                evt_type = "plan"
            title = str(body.get("title") or "").strip()
            if not title:
                raise ValueError("title required")
            if evt_type == "plan":
                st_time = body.get("stTime") or body.get("dueAt") or body.get("at")
                if not st_time:
                    raise ValueError("stTime required")
                return crud.createPlanEvt(
                    db,
                    title=title,
                    stTime=str(st_time),
                    durationMin=int(body.get("durationMin") or 30),
                    desc=body.get("desc") or body.get("description"),
                    prio=body.get("prio") or body.get("priority") or "mid",
                    src="openclaw",
                )
            if evt_type == "ddl":
                end_time = body.get("endTime") or body.get("ddlAt") or body.get("at")
                if not end_time:
                    raise ValueError("endTime required")
                return crud.createDdlEvt(
                    db,
                    title=title,
                    endTime=str(end_time),
                    hardDdl=bool(body.get("hardDdl", False)),
                    desc=body.get("desc") or body.get("description"),
                    prio=body.get("prio") or body.get("priority") or "high",
                    src="openclaw",
                )
            if evt_type == "course":
                required = ("courseName", "stTime", "endTime", "stDate", "endDate", "weekDay")
                missing = [key for key in required if body.get(key) in (None, "")]
                if missing:
                    raise ValueError(f"required fields missing: {', '.join(missing)}")
                return crud.createCourseEvt(
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
            raise ValueError("unsupported evtType")

        return _run_write(db, operation)

    @router.post("/evtUpdate", dependencies=protected)
    @router.post("/db/update_event", dependencies=protected)
    def evtUpdate(body: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
        evt_id = body.get("evtId") or body.get("eventId")
        if not evt_id:
            return _failed(["evtId required"])
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
            normalized = aliases.get(key, key)
            if normalized in allowed:
                patch[normalized] = value
        if not patch:
            return _failed(["no supported update fields"])
        return _run_write(db, lambda: crud.updateEvt(db, str(evt_id), **patch))

    @router.post("/evtDelete", dependencies=protected)
    @router.post("/db/delete_event", dependencies=protected)
    def evtDelete(body: dict[str, Any], db: Session = Depends(get_db), scope: AgentScope = Depends(require_agent_scope)) -> dict[str, Any]:
        evt_id = body.get("evtId") or body.get("eventId")
        if not evt_id:
            return _failed(["evtId required"])
        event = db.get(EvtBase, str(evt_id))
        if event is None or event.userId != scope.userId:
            return _failed([f"evt not found: {evt_id}"])
        return _run_write(db, lambda: crud.cancelEvt(db, str(evt_id), src="openclaw"))

    @router.post("/ideaCapture", dependencies=protected)
    @router.post("/idea/capture", dependencies=protected)
    def ideaCapture(body: dict[str, Any], db: Session = Depends(get_db), scope: AgentScope = Depends(require_agent_scope)) -> dict[str, Any]:
        content = str(body.get("content") or "").strip()
        if not content:
            return _failed(["content required"])
        return _run_write(
            db,
            lambda: crud.createIdea(
                db,
                content=content,
                srcType=str(body.get("srcType") or "text"),
                mediaPath=body.get("mediaPath"),
                userId=scope.userId,
            ),
        )

    @router.post("/ideaToEvt", dependencies=protected)
    @router.post("/idea/to_event", dependencies=protected)
    def ideaToEvt(body: dict[str, Any], db: Session = Depends(get_db), scope: AgentScope = Depends(require_agent_scope)) -> dict[str, Any]:
        idea_id = body.get("ideaId")
        if not idea_id:
            return _failed(["ideaId required"])

        def operation() -> dict[str, Any]:
            idea = db.get(Idea, str(idea_id))
            if idea is None or idea.userId != scope.userId:
                raise ValueError(f"idea not found: {idea_id}")
            evt_type = str(body.get("evtType") or "plan").lower()
            if evt_type == "life":
                evt_type = "plan"
            title = str(body.get("title") or "").strip()
            if not title:
                title = str(idea.content)[:300]
            if evt_type == "ddl":
                end_time = body.get("endTime") or body.get("ddlAt") or body.get("at")
                if not end_time:
                    raise ValueError("endTime required")
                event = crud.createDdlEvt(
                    db,
                    title=title,
                    endTime=str(end_time),
                    hardDdl=bool(body.get("hardDdl", False)),
                    desc=body.get("desc"),
                    prio=body.get("prio", "high"),
                    userId=scope.userId,
                    src="openclaw",
                )
            else:
                st_time = body.get("stTime") or body.get("dueAt") or body.get("at")
                if not st_time:
                    raise ValueError("stTime required")
                event = crud.createPlanEvt(
                    db,
                    title=title,
                    stTime=str(st_time),
                    durationMin=int(body.get("durationMin") or 30),
                    desc=body.get("desc"),
                    prio=body.get("prio", "mid"),
                    userId=scope.userId,
                    src="openclaw",
                )
            crud.updateIdea(db, str(idea_id), handled=True)
            return {"event": event, "ideaId": idea_id, "handled": True}

        return _run_write(db, operation)

    @router.post("/sendText", dependencies=protected)
    @router.post("/feedback/send_text", dependencies=protected)
    def sendText(
        body: dict[str, Any],
        settings: Settings = Depends(get_settings),
    ) -> dict[str, Any]:
        text = body.get("text")
        if not isinstance(text, str) or not text.strip():
            return _failed(["text required"])
        receive_id = _resolveReceiveId(body, settings)
        if not receive_id:
            return _failed(["receiveId/chatId required or configure FEISHU_DEFAULT_CHAT_ID"])
        client = _getFeishuClient(settings)
        if client is None:
            return _failed(["feishu not configured"])
        try:
            return _done(client.send_text(receive_id, text.strip()))
        except FeishuAPIError as exc:
            return _failed([str(exc)])

    @router.post("/sendCard", dependencies=protected)
    @router.post("/feedback/send_card", dependencies=protected)
    @router.post("/feedback/send_query_result_card", dependencies=protected)
    @router.post("/feedback/send_operation_success_card", dependencies=protected)
    @router.post("/feedback/send_reminder_card", dependencies=protected)
    def sendCard(
        body: dict[str, Any],
        settings: Settings = Depends(get_settings),
    ) -> dict[str, Any]:
        card = body.get("card")
        if not isinstance(card, dict):
            return _failed(["card required"])
        receive_id = _resolveReceiveId(body, settings)
        if not receive_id:
            return _failed(["receiveId/chatId required or configure FEISHU_DEFAULT_CHAT_ID"])
        client = _getFeishuClient(settings)
        if client is None:
            return _failed(["feishu not configured"])
        try:
            return _done(client.send_interactive_card(receive_id, card))
        except FeishuAPIError as exc:
            return _failed([str(exc)])

    @router.post("/screenPush", dependencies=protected)
    @router.post("/feedback/screen_push", dependencies=protected)
    async def screenPush(body: dict[str, Any], scope: AgentScope = Depends(require_agent_scope)) -> dict[str, Any]:
        delivered = await screenManager.broadcast(
            {
                "kind": "reminder",
                "evtId": body.get("evtId"),
                "title": body.get("title", ""),
                "content": body.get("content", ""),
            },
            userId=scope.userId,
        )
        return {
            "ok": delivered > 0,
            "stat": "done" if delivered else "offline",
            "data": {"delivered": delivered},
            "errors": [] if delivered else ["screen offline"],
        }

    return router


def createDevRouter() -> APIRouter:
    router = APIRouter(tags=["device"])

    @router.post("/dev/state", dependencies=[Depends(requireDeviceToken)])
    async def postDevState(body: DevStateBody, db: Session = Depends(get_db)) -> dict[str, Any]:
        state = crud.upsertDevState(
            db,
            devId=body.devId,
            state=body.state,
            confidence=body.confidence,
            seenAt=body.seenAt,
            meta=body.meta,
        )
        await screenManager.broadcast(
            {
                "kind": "devState",
                "devId": state["deviceId"],
                "deviceId": state["deviceId"],
                "state": state["state"],
                "confidence": state.get("confidence"),
                "seenAt": state.get("seenAt"),
                "meta": state.get("meta"),
            }
        )
        return {"ok": True, "data": state}

    return router
