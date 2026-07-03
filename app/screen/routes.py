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
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@600;700&display=swap" rel="stylesheet">
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
    <div class="pane-head">
      <span>提醒</span>
      <span id="lastMsgAt">等待消息</span>
    </div>
    <div id="reminderArea" data-ws-ui="reminder" class="empty">暂无提醒</div>
    <div class="hint-row">
      <span>副屏模式</span>
      <span id="heartbeat">--</span>
    </div>
  </section>
</main>
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
                "devId": latest["devId"],
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
