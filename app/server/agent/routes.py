from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.server.agent.scope import (
    SCOPE_HEADER,
    AgentScope,
    enforce_restricted_agent_scope,
    require_agent_scope,
)
from app.server.config import Settings, get_settings
from app.server.db.session import get_db
from app.server.new_core import crud
from app.server.new_core.models import Idea, IdeaMediaJob, IdeaUpload, nowIso
from app.server.screen.manager import screenManager

AGENT_TOKEN_HEADER = "X-SmartCore-Agent-Token"
DEVICE_TOKEN_HEADER = "X-SmartCore-Device-Token"
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
        "name": "dailyWorkContext",
        "method": "GET",
        "path": "/agent/daily-work-context",
        "riskLevel": "read",
        "confirmationRequired": False,
        "inputSchema": _schema_object(
            {
                "date": {"type": "string", "format": "date"},
                "timezone": {"type": "string", "default": "Asia/Shanghai"},
            },
            ["date"],
        ),
    },
    {
        "name": "evtQuery",
        "method": "POST",
        "path": "/agent/db/query_events",
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
        "name": "computerWorkBlockContext",
        "method": "GET",
        "path": "/agent/computer/work-block-context",
        "riskLevel": "read",
        "confirmationRequired": False,
        "inputSchema": _schema_object(
            {"runId": {"type": "string"}},
            ["runId"],
        ),
    },
    {
        "name": "computerWorkBlockAnalysisComplete",
        "method": "POST",
        "path": "/agent/computer/work-block-analysis",
        "riskLevel": "write",
        "confirmationRequired": False,
        "inputSchema": _schema_object(
            {
                "runId": {"type": "string"},
                "status": {"type": "string", "enum": ["complete", "failed"]},
                "action": {
                    "type": "string",
                    "enum": ["start", "extend", "switch", "complete", "ignore"],
                },
                "topicKey": {"type": "string", "maxLength": 100},
                "title": {"type": "string", "maxLength": 20},
                "summary": {"type": "string", "maxLength": 800},
                "progress": {"type": "string", "maxLength": 300},
                "outcome": {"type": "string", "maxLength": 300},
                "blocker": {"type": "string", "maxLength": 300},
                "nextStep": {"type": "string", "maxLength": 300},
                "planSemanticAssessments": {"type": "array"},
                "evidenceContextIds": {"type": "array"},
                "model": {
                    "type": "string",
                    "enum": [
                        "qwen3.7-plus",
                        "deepseek-v4-flash",
                        "deepseek-v4-flash-0731",
                    ],
                },
                "promptVersion": {
                    "type": "string",
                    "enum": ["computer-work-block-v1"],
                },
                "errorMessage": {"type": "string", "maxLength": 1000},
            },
            ["runId", "status"],
        ),
    },
    {
        "name": "computerHourlyContext",
        "method": "GET",
        "path": "/agent/computer/hourly-context",
        "riskLevel": "read",
        "confirmationRequired": False,
        "inputSchema": _schema_object(
            {
                "deviceId": {"type": "string"},
                "hourStart": {"type": "string", "format": "date-time"},
                "timezone": {"type": "string"},
            },
            ["deviceId", "hourStart"],
        ),
    },
    {
        "name": "computerHourlyAnalysisComplete",
        "method": "POST",
        "path": "/agent/computer/hourly-analysis",
        "riskLevel": "write",
        "confirmationRequired": False,
        "inputSchema": _schema_object(
            {
                "deviceId": {"type": "string"},
                "hourStart": {"type": "string", "format": "date-time"},
                "status": {"type": "string", "enum": ["complete", "failed"]},
                "title": {"type": "string", "maxLength": 10},
                "summary": {"type": "string", "maxLength": 800},
                "planAssessments": {"type": "array"},
                "topics": {"type": "array"},
                "evidence": {"type": "object"},
                "model": {
                    "type": "string",
                    "enum": [
                        "qwen3.7-plus",
                        "deepseek-v4-flash",
                        "deepseek-v4-flash-0731",
                    ],
                },
                "promptVersion": {"type": "string", "enum": ["computer-analysis-v1"]},
            },
            ["deviceId", "hourStart", "status"],
        ),
    },
    {
        "name": "computerDailyContext",
        "method": "GET",
        "path": "/agent/computer/daily-context",
        "riskLevel": "read",
        "confirmationRequired": False,
        "inputSchema": _schema_object(
            {"deviceId": {"type": "string"}, "date": {"type": "string", "format": "date"}},
            ["deviceId", "date"],
        ),
    },
    {
        "name": "computerDailyLogComplete",
        "method": "POST",
        "path": "/agent/computer/daily-log",
        "riskLevel": "write",
        "confirmationRequired": False,
        "inputSchema": _schema_object(
            {
                "deviceId": {"type": "string"},
                "logDate": {"type": "string", "format": "date"},
                "status": {"type": "string", "enum": ["complete", "failed"]},
                "title": {"type": "string", "maxLength": 10},
                "summary": {"type": "string", "maxLength": 1200},
                "topics": {"type": "array"},
                "planAssessments": {"type": "array"},
                "reminderSummary": {"type": "array"},
                "hourlyAnalysisIds": {"type": "array"},
                "workBlockIds": {"type": "array"},
                "phase": {"type": "string", "enum": ["preview", "final"]},
                "model": {
                    "type": "string",
                    "enum": [
                        "qwen3.7-plus",
                        "deepseek-v4-flash",
                        "deepseek-v4-flash-0731",
                    ],
                },
                "promptVersion": {
                    "type": "string",
                    "enum": ["computer-analysis-v1", "computer-work-block-v1"],
                },
            },
            ["deviceId", "logDate", "status"],
        ),
    },
    {
        "name": "evtCreate",
        "method": "POST",
        "path": "/agent/db/create_event",
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
        "name": "commutePlanUpdate",
        "method": "POST",
        "path": "/agent/db/update_commute_plan",
        "riskLevel": "write",
        "confirmationRequired": False,
        "description": (
            "Atomically update an existing commute Plan and its existing standalone departure "
            "reminder. Plan start is computed as departureAt plus commuteMinutes; this tool never "
            "creates a departure reminder."
        ),
        "inputSchema": _schema_object(
            {
                "planEvtId": {"type": "string", "minLength": 1},
                "reminderEvtId": {"type": "string", "minLength": 1},
                "departureAt": {
                    "type": "string",
                    "format": "date-time",
                    "description": "Absolute departure date-time with a UTC offset.",
                },
                "commuteMinutes": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 1440,
                },
                "endAt": {
                    "type": "string",
                    "format": "date-time",
                    "description": "Absolute Plan end date-time with a UTC offset.",
                },
            },
            ["planEvtId", "reminderEvtId", "departureAt", "commuteMinutes", "endAt"],
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
        "riskLevel": "destructive",
        "confirmationRequired": False,
        "inputSchema": _schema_object({"evtId": {"type": "string", "minLength": 1}}, ["evtId"]),
    },
    {
        "name": "ideaCapture",
        "method": "POST",
        "path": "/agent/idea/capture",
        "riskLevel": "write",
        "confirmationRequired": False,
        "inputSchema": _schema_object(
            {
                "title": {"type": "string", "minLength": 1, "maxLength": 300},
                "description": {"type": "string", "maxLength": 4000},
                "srcType": {"type": "string", "enum": ["text", "voice", "media"]},
                "uploadIds": {"type": "array", "items": {"type": "string"}},
            },
            ["title"],
        ),
    },
    {
        "name": "ideaMediaJobComplete",
        "method": "POST",
        "path": "/agent/idea/media-job/complete",
        "riskLevel": "write",
        "confirmationRequired": False,
        "inputSchema": _schema_object(
            {
                "jobId": {"type": "string", "minLength": 1},
                "summary": {"type": "string", "minLength": 1, "maxLength": 100},
            },
            ["jobId", "summary"],
        ),
    },
    {
        "name": "ideaMediaJobFail",
        "method": "POST",
        "path": "/agent/idea/media-job/fail",
        "riskLevel": "write",
        "confirmationRequired": False,
        "inputSchema": _schema_object(
            {
                "jobId": {"type": "string", "minLength": 1},
                "errorMessage": {"type": "string", "minLength": 1, "maxLength": 300},
            },
            ["jobId", "errorMessage"],
        ),
    },
    {
        "name": "ideaToEvt",
        "method": "POST",
        "path": "/agent/idea/to_event",
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

def _failed(errors: list[str]) -> dict[str, Any]:
    return {"ok": False, "stat": "failed", "data": None, "errors": errors}


def _done(data: Any) -> dict[str, Any]:
    return {"ok": True, "stat": "done", "data": data, "errors": []}


def _run_write(db: Session, operation: Callable[[], Any]) -> dict[str, Any]:
    try:
        return _done(operation())
    except (ValueError, TypeError, IntegrityError) as exc:
        db.rollback()
        return _failed([str(exc)])


def requireAgentToken(
    request: Request,
    settings: Settings = Depends(get_settings),
    x_smartcore_agent_token: str | None = Header(default=None, alias=AGENT_TOKEN_HEADER),
    x_smartcore_agent_scope: str | None = Header(default=None, alias=SCOPE_HEADER),
) -> None:
    expected = settings.agent_api_token
    if expected and x_smartcore_agent_token != expected:
        raise HTTPException(status_code=401, detail="invalid or missing agent token")
    enforce_restricted_agent_scope(request, x_smartcore_agent_scope)


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

    @router.post("/idea/capture", dependencies=protected)
    def ideaCapture(
        body: dict[str, Any],
        db: Session = Depends(get_db),
        scope: AgentScope = Depends(require_agent_scope),
    ) -> dict[str, Any]:
        title = str(body.get("title") or "").strip()
        if not title:
            return _failed(["title required"])
        upload_ids = [str(item) for item in body.get("uploadIds", []) if str(item)]
        if upload_ids:
            uploads = db.scalars(
                select(IdeaUpload).where(
                    IdeaUpload.uploadId.in_(upload_ids), IdeaUpload.userId == scope.userId
                )
            ).all()
            if len(uploads) != len(set(upload_ids)):
                return _failed(["one or more attachments are unavailable"])
        return _run_write(
            db,
            lambda: crud.createIdea(
                db,
                title=title,
                description=str(body.get("description") or ""),
                srcType=str(body.get("srcType") or "text"),
                uploadIds=upload_ids,
                userId=scope.userId,
            ),
        )

    @router.post("/idea/media-job/complete", dependencies=protected)
    def ideaMediaJobComplete(
        body: dict[str, Any],
        db: Session = Depends(get_db),
        scope: AgentScope = Depends(require_agent_scope),
    ) -> dict[str, Any]:
        job_id = str(body.get("jobId") or "").strip()
        summary = str(body.get("summary") or "").strip()
        if not job_id or not summary:
            return _failed(["jobId and summary required"])
        if len(summary) > 100:
            return _failed(["summary must be at most 100 characters"])
        job = db.get(IdeaMediaJob, job_id)
        if job is None or job.userId != scope.userId:
            return _failed(["media job not found"])
        if job.stat in {"ready", "consumed"}:
            return _done({"jobId": job.jobId, "stat": job.stat, "summary": job.summary})
        if job.stat not in {"queued", "processing", "ocr_ready"}:
            return _failed([f"media job cannot complete from state {job.stat}"])
        job.stat = "ready"
        job.summary = summary
        job.errorMessage = None
        job.updatedAt = nowIso()
        db.commit()
        return _done({"jobId": job.jobId, "stat": job.stat, "summary": job.summary})

    @router.post("/idea/media-job/fail", dependencies=protected)
    def ideaMediaJobFail(
        body: dict[str, Any],
        db: Session = Depends(get_db),
        scope: AgentScope = Depends(require_agent_scope),
    ) -> dict[str, Any]:
        job_id = str(body.get("jobId") or "").strip()
        job = db.get(IdeaMediaJob, job_id)
        if job is None or job.userId != scope.userId:
            return _failed(["media job not found"])
        if job.stat not in {"ready", "consumed"}:
            job.stat = "failed"
            job.errorMessage = str(body.get("errorMessage") or "media processing failed")[:300]
            job.updatedAt = nowIso()
            db.commit()
        return _done({"jobId": job.jobId, "stat": job.stat})

    @router.post("/idea/to_event", dependencies=protected)
    def ideaToEvt(
        body: dict[str, Any],
        db: Session = Depends(get_db),
        scope: AgentScope = Depends(require_agent_scope),
    ) -> dict[str, Any]:
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
                title = str(idea.title)[:300]
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
            crud.updateIdea(
                db,
                str(idea_id),
                userId=scope.userId,
                handled=True,
            )
            return {"event": event, "ideaId": idea_id, "handled": True}

        return _run_write(db, operation)

    @router.post("/feedback/screen_push", dependencies=protected)
    async def screenPush(
        body: dict[str, Any], scope: AgentScope = Depends(require_agent_scope)
    ) -> dict[str, Any]:
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
        try:
            state = crud.upsertDevState(
                db,
                devId=body.devId,
                state=body.state,
                confidence=body.confidence,
                seenAt=body.seenAt,
                meta=body.meta,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="device not found") from exc
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
