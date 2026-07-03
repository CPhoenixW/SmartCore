from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.session import get_db
from app.feishu.client import FeishuAPIError, FeishuClient
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

_feishuClient: FeishuClient | None = None


def _getFeishuClient(settings: Settings) -> FeishuClient | None:
    if not settings.feishu_app_id or not settings.feishu_app_secret:
        return None
    global _feishuClient
    if _feishuClient is None:
        _feishuClient = FeishuClient(settings.feishu_app_id, settings.feishu_app_secret)
    return _feishuClient


def _resolveReceiveId(body: dict[str, Any], settings: Settings) -> str | None:
    for key in ("receiveId", "receive_id", "chatId", "chat_id"):
        value = body.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    default = settings.feishu_default_chat_id
    return default if default else None


def _failed(errors: list[str]) -> dict[str, Any]:
    return {"ok": False, "stat": "failed", "errors": errors}


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
            return _failed(["evtId required"])
        update_fields = (
            "title",
            "desc",
            "prio",
            "stat",
            "dueAt",
            "doneAt",
            "ddlAt",
            "hardDdl",
            "classDate",
            "attendStat",
        )
        patch = {key: body[key] for key in update_fields if key in body}
        try:
            data = crud.updateEvt(db, evtId, **patch)
        except ValueError as exc:
            return _failed([str(exc)])
        return {"ok": True, "stat": "done", "data": data}

    @router.post("/evtDelete", dependencies=[Depends(requireAgentToken)])
    def evtDelete(body: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
        evtId = body.get("evtId")
        if not evtId:
            return _failed(["evtId required"])
        try:
            data = crud.cancelEvt(db, evtId, src="openclaw")
        except ValueError as exc:
            return _failed([str(exc)])
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
        ideaId = body.get("ideaId")
        if not ideaId:
            return _failed(["ideaId required"])
        try:
            data = crud.ideaToLifeEvt(
                db,
                ideaId=ideaId,
                title=body.get("title", ""),
                dueAt=body.get("dueAt"),
                src="openclaw",
            )
        except ValueError as exc:
            return _failed([str(exc)])
        return {"ok": True, "stat": "done", "data": data}

    @router.post("/sendText", dependencies=[Depends(requireAgentToken)])
    def sendText(
        body: dict[str, Any],
        settings: Settings = Depends(get_settings),
    ) -> dict[str, Any]:
        text = body.get("text")
        if not isinstance(text, str) or not text.strip():
            return _failed(["text required"])
        receive_id = _resolveReceiveId(body, settings)
        if not receive_id:
            return _failed(["receiveId/chat_id required or configure FEISHU_DEFAULT_CHAT_ID"])
        client = _getFeishuClient(settings)
        if client is None:
            return _failed(["feishu not configured"])
        try:
            data = client.send_text(receive_id, text.strip())
        except FeishuAPIError as exc:
            return _failed([str(exc)])
        return {"ok": True, "stat": "done", "data": data}

    @router.post("/sendCard", dependencies=[Depends(requireAgentToken)])
    def sendCard(
        body: dict[str, Any],
        settings: Settings = Depends(get_settings),
    ) -> dict[str, Any]:
        card = body.get("card")
        if not isinstance(card, dict):
            return _failed(["card required"])
        receive_id = _resolveReceiveId(body, settings)
        if not receive_id:
            return _failed(["receiveId/chat_id required or configure FEISHU_DEFAULT_CHAT_ID"])
        client = _getFeishuClient(settings)
        if client is None:
            return _failed(["feishu not configured"])
        try:
            data = client.send_interactive_card(receive_id, card)
        except FeishuAPIError as exc:
            return _failed([str(exc)])
        return {"ok": True, "stat": "done", "data": data}

    @router.post("/screenPush", dependencies=[Depends(requireAgentToken)])
    async def screenPush(body: dict[str, Any]) -> dict[str, Any]:
        delivered = await screenManager.broadcast(
            {
                "kind": "reminder",
                "title": body.get("title", ""),
                "content": body.get("content", ""),
            }
        )
        return {
            "ok": delivered > 0,
            "stat": "done" if delivered else "offline",
            "delivered": delivered,
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
                "devId": state["devId"],
                "state": state["state"],
                "confidence": state.get("confidence"),
                "seenAt": state.get("seenAt"),
                "meta": state.get("meta"),
            }
        )
        return {"ok": True, "data": state}

    return router
