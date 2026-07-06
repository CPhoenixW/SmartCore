# ruff: noqa: E501
from __future__ import annotations

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.new_core import crud
from app.screen.manager import screenManager

router = APIRouter(tags=["screen"])

_SCREEN_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no">
<title>SmartCore Screen</title>
<link rel="stylesheet" crossorigin="anonymous" href="https://cdn.jsdelivr.net/npm/misans@4.1.0/lib/Latin/MiSansLatin-Medium.min.css">
<link rel="stylesheet" href="/static/screen/screen.css">
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
        <span class="pane-label">Latest Reminder</span>
      </div>
      <div id="latestReminderList" class="today-list empty">No active reminder</div>
    </div>
    <div class="reminder-zone day-plan">
      <div class="pane-head">
        <span class="pane-label">Today</span>
        <span id="lastMsgAt" class="pane-meta">—</span>
      </div>
      <div id="todayEvtList" class="today-list empty">No events today</div>
    </div>
    <div class="reminder-zone expired">
      <div class="pane-head">
        <span class="pane-label">Expired</span>
      </div>
      <div id="expiredReminderList" class="today-list empty">No expired reminders</div>
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
<script src="/static/screen/screen.js"></script>
</body>
</html>"""


@router.get("/screen", response_class=HTMLResponse)
def screenPage() -> str:
    return _SCREEN_HTML


@router.websocket("/screen/ws")
async def screenWebsocket(
    websocket: WebSocket,
    db: Session = Depends(get_db),
) -> None:
    await screenManager.connect(websocket)
    latest = crud.getLatestDevState(db, devId="pi")
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
            await websocket.receive_text()
    except WebSocketDisconnect:
        await screenManager.disconnect(websocket)
