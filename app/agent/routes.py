from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.session import get_db
from app.new_core import crud
from app.screen.manager import screenManager

AGENT_TOKEN_HEADER = "X-SmartCore-Agent-Token"
DEVICE_TOKEN_HEADER = "X-SmartCore-Device-Token"

_AGENT_TOOLS: list[dict[str, Any]] = [
    {"name": "evtQuery", "method": "POST", "path": "/agent/evtQuery"},
    {"name": "evtCreate", "method": "POST", "path": "/agent/evtCreate"},
    {"name": "evtUpdate", "method": "POST", "path": "/agent/evtUpdate"},
    {"name": "evtDelete", "method": "POST", "path": "/agent/evtDelete"},
    {"name": "ideaCapture", "method": "POST", "path": "/agent/ideaCapture"},
    {"name": "ideaToEvt", "method": "POST", "path": "/agent/ideaToEvt"},
    {"name": "sendText", "method": "POST", "path": "/agent/sendText"},
    {"name": "sendCard", "method": "POST", "path": "/agent/sendCard"},
    {"name": "screenPush", "method": "POST", "path": "/agent/screenPush"},
]


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

    @router.get("/tools", dependencies=[Depends(requireAgentToken)])
    def listTools() -> dict[str, list[dict[str, Any]]]:
        return {"tools": _AGENT_TOOLS}

    @router.post("/evtQuery", dependencies=[Depends(requireAgentToken)])
    def evtQuery(
        body: dict[str, Any] | None = None,
        db: Session = Depends(get_db),
    ) -> dict[str, Any]:
        events = crud.listEvt(db)
        return {"ok": True, "stat": "done", "data": {"events": events}}

    @router.post("/evtCreate", dependencies=[Depends(requireAgentToken)])
    def evtCreate(body: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
        evtType = body.get("evtType")
        title = body.get("title", "")
        if evtType == "life":
            data = crud.createLifeEvt(db, title=title, dueAt=body.get("dueAt"), src="openclaw")
        elif evtType == "ddl":
            data = crud.createDdlEvt(
                db,
                title=title,
                ddlAt=body.get("ddlAt"),
                hardDdl=bool(body.get("hardDdl", False)),
                src="openclaw",
            )
        else:
            return {"ok": False, "stat": "failed", "errors": ["unsupported evtType"]}
        return {"ok": True, "stat": "done", "data": data}

    @router.post("/evtUpdate", dependencies=[Depends(requireAgentToken)])
    def evtUpdate(body: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
        evtId = body.get("evtId")
        if not evtId:
            return {"ok": False, "stat": "failed", "errors": ["evtId required"]}
        patch = {key: body[key] for key in ("title", "desc", "prio", "stat") if key in body}
        data = crud.updateEvt(db, evtId, **patch)
        return {"ok": True, "stat": "done", "data": data}

    @router.post("/evtDelete", dependencies=[Depends(requireAgentToken)])
    def evtDelete(body: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
        evtId = body.get("evtId")
        if not evtId:
            return {"ok": False, "stat": "failed", "errors": ["evtId required"]}
        data = crud.cancelEvt(db, evtId, src="openclaw")
        return {"ok": True, "stat": "done", "data": data}

    @router.post("/ideaCapture", dependencies=[Depends(requireAgentToken)])
    def ideaCapture(body: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
        data = crud.createIdea(
            db,
            content=body.get("content", ""),
            srcType=body.get("srcType", "text"),
        )
        return {"ok": True, "stat": "done", "data": data}

    @router.post("/ideaToEvt", dependencies=[Depends(requireAgentToken)])
    def ideaToEvt(body: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
        data = crud.ideaToLifeEvt(
            db,
            ideaId=body["ideaId"],
            title=body.get("title", ""),
            dueAt=body.get("dueAt"),
            src="openclaw",
        )
        return {"ok": True, "stat": "done", "data": data}

    @router.post("/sendText", dependencies=[Depends(requireAgentToken)])
    def sendText(body: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "stat": "done", "data": {"text": body.get("text", "")}}

    @router.post("/sendCard", dependencies=[Depends(requireAgentToken)])
    def sendCard(body: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "stat": "done", "data": body}

    @router.post("/screenPush", dependencies=[Depends(requireAgentToken)])
    async def screenPush(body: dict[str, Any]) -> dict[str, Any]:
        await screenManager.broadcast(
            {
                "kind": "reminder",
                "title": body.get("title", ""),
                "content": body.get("content", ""),
            }
        )
        return {"ok": True, "stat": "done"}

    return router


def createDevRouter() -> APIRouter:
    router = APIRouter(tags=["device"])

    @router.post("/dev/state", dependencies=[Depends(requireDeviceToken)])
    def postDevState(body: DevStateBody, db: Session = Depends(get_db)) -> dict[str, Any]:
        state = crud.upsertDevState(
            db,
            devId=body.devId,
            state=body.state,
            confidence=body.confidence,
            seenAt=body.seenAt,
            meta=body.meta,
        )
        return {"ok": True, "data": state}

    return router
