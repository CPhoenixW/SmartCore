# ruff: noqa: E501
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.server.config import get_settings
from app.server.db.session import get_db
from app.server.new_core import crud
from app.server.new_core.event_relations import list_events
from app.server.new_core.models import DeviceKey, EvtBase, LifeDevice, nowIso
from app.server.screen.manager import credential_active, screenManager
from app.server.screen.tickets import screenTickets
from app.server.user_device.service import requireDevice, tokenHash

router = APIRouter(tags=["screen"])
DEVICE_TOKEN_HEADER = "X-SmartCore-Device-Token"


class ScreenReminderActionBody(BaseModel):
    evtId: str
    action: str


def _screen_device(db: Session, deviceId: str, token: str | None) -> LifeDevice:
    device = requireDevice(db, token)
    if device.deviceId != deviceId or device.deviceKind != "screen":
        raise HTTPException(status_code=403, detail="screen credential required")
    return device

_SCREEN_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no">
<title>SmartCore Screen</title>
<link rel="stylesheet" crossorigin="anonymous" href="https://cdn.jsdelivr.net/npm/misans@4.1.0/lib/Normal/MiSans-Regular.min.css">
<link rel="stylesheet" crossorigin="anonymous" href="https://cdn.jsdelivr.net/npm/misans@4.1.0/lib/Latin/MiSansLatin-Medium.min.css">
<link rel="stylesheet" href="/static/screen/screen.css">
<link rel="stylesheet" href="/static/screen/screen_overrides.css">
</head>
<body data-app="smartcore-screen" data-theme="light">
<main class="screen-shell">
  <section class="time-pane">
    <div class="brand-row">
      <span>SmartCore</span>
      <div id="wsStatus" data-ws-ui="status"><span class="dot"></span><span id="wsStatusText">连接中</span></div>
    </div>
    <div class="clock-stack">
      <div id="clock" class="digit-clock" data-ws-ui="clock" aria-hidden="true">
        <span id="clockHours">--</span><span id="clockSep" class="digit-sep">:</span><span id="clockMins">--</span>
      </div>
      <div id="clockDate" class="clock-date">—</div>
    </div>
    <div class="state-row">
      <div class="state-copy">
        <span class="state-label">当前状态</span>
        <span id="stateCaption" class="state-caption">状态未知</span>
      </div>
      <span id="currentState" data-ws-ui="state" class="unknown">unknown</span>
    </div>
  </section>
  <section class="info-pane">
    <div class="reminder-zone latest">
      <div class="pane-head">
        <span class="pane-label">当前安排</span>
      </div>
      <div id="latestReminderList" class="today-list empty"></div>
    </div>
    <div class="reminder-zone day-plan">
      <div class="pane-head">
        <span class="pane-label">今日其他</span>
        <span id="lastMsgAt" class="pane-meta">—</span>
      </div>
      <div id="todayEvtList" class="today-list empty"></div>
    </div>
    <div class="reminder-zone expired">
      <div class="pane-head">
        <span class="pane-label">已逾期</span>
      </div>
      <div id="expiredReminderList" class="today-list empty"></div>
    </div>
  </section>
</main>
<section id="reminderPage" data-ws-ui="reminder" class="reminder-page" aria-live="assertive" aria-hidden="true">
  <div class="reminder-shell">
    <span class="reminder-kicker">Reminder</span>
    <h1 id="reminderPageTitle">提醒</h1>
    <p id="reminderPageContent">—</p>
    <div class="reminder-actions">
      <button id="reminderDone" type="button">已完成</button>
      <button id="reminderSnooze" type="button">延时 10 分钟</button>
    </div>
  </div>
</section>
<section id="screenSetup" class="screen-setup" hidden>
  <div><strong>连接 SmartCore 副屏</strong><p id="screenSetupText">正在确认设备凭据…</p></div>
</section>
<script src="/static/screen/screen.js"></script>
</body>
</html>"""


@router.get("/screen", response_class=HTMLResponse)
def screenPage() -> str:
    return _SCREEN_HTML


@router.get("/screen/events")
def screenEvents(
    deviceId: str = Query(min_length=1, max_length=50),
    db: Session = Depends(get_db),
    token: str | None = Header(default=None, alias=DEVICE_TOKEN_HEADER),
) -> dict:
    device = _screen_device(db, deviceId, token)
    return {"ok": True, "data": list_events(db, user_id=device.userId, evt_types=["plan"], include_course_templates=False)}


@router.post("/screen/reminder/action")
def screenReminderAction(
    body: ScreenReminderActionBody,
    deviceId: str = Query(min_length=1, max_length=50),
    db: Session = Depends(get_db),
    token: str | None = Header(default=None, alias=DEVICE_TOKEN_HEADER),
) -> dict:
    device = _screen_device(db, deviceId, token)
    event = db.get(EvtBase, body.evtId)
    if event is None or event.userId != device.userId:
        raise HTTPException(status_code=404, detail="event not found")
    try:
        data = crud.applyReminderAction(db, evtId=body.evtId, action=body.action, now=nowIso(), src="screen")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "data": data}


@router.post("/screen/ws-ticket")
def screenTicket(
    deviceId: str = Query(min_length=1, max_length=50),
    db: Session = Depends(get_db),
    token: str | None = Header(default=None, alias=DEVICE_TOKEN_HEADER),
) -> dict:
    device = _screen_device(db, deviceId, token)
    return {"ok": True, "data": {"ticket": screenTickets.issue(device.deviceId, tokenHash(token)), "expiresIn": 60}}


@router.websocket("/screen/ws")
async def screenWebsocket(
    websocket: WebSocket,
    db: Session = Depends(get_db),
) -> None:
    device_id = websocket.query_params.get("deviceId")
    token = websocket.query_params.get("deviceToken")
    try:
        origin = websocket.headers.get("origin")
        settings = get_settings()
        if settings.public_access_enabled and origin != settings.public_origin:
            raise HTTPException(status_code=403, detail="invalid screen origin")
        ticket = websocket.query_params.get("ticket")
        if ticket:
            token_hash = screenTickets.consume(ticket, device_id or "")
            key = db.scalar(select(DeviceKey).where(DeviceKey.tokenHash == token_hash))
            device = db.get(LifeDevice, key.deviceId) if key else None
            if device is None or not credential_active(device.userId, device.deviceId, token_hash):
                raise HTTPException(status_code=401, detail="invalid screen credential")
        elif not settings.public_access_enabled:
            device = _screen_device(db, device_id or "", token)
            token_hash = tokenHash(token)
        else:
            raise HTTPException(status_code=401, detail="connection ticket required")
    except HTTPException:
        await websocket.close(code=1008)
        return
    await screenManager.connect(websocket, device.userId, device.deviceId, token_hash)
    pi = db.scalar(select(LifeDevice).where(LifeDevice.userId == device.userId, LifeDevice.deviceKind == "pi", LifeDevice.stat == "active").order_by(LifeDevice.lastSeenAt.desc()))
    latest = crud.getLatestDevState(db, devId=pi.deviceId) if pi else None
    if latest:
        await websocket.send_json(
            {
                "kind": "devState",
                "devId": latest["deviceId"],
                "deviceId": latest["deviceId"],
                "state": latest["state"],
                "confidence": latest["confidence"],
                "seenAt": latest["seenAt"],
                "meta": latest["meta"],
            }
        )
    try:
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=20)
            except TimeoutError:
                pass
            if not await screenManager.authorize(websocket):
                return
            await websocket.send_json({"kind": "ping"})
    except WebSocketDisconnect:
        pass
    finally:
        await screenManager.disconnect(websocket)
