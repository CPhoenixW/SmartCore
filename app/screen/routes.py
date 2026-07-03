# ruff: noqa: E501
from __future__ import annotations

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.new_core import crud
from app.screen.manager import screenManager

router = APIRouter(tags=["screen"])


@router.get("/screen", response_class=HTMLResponse)
def screenPage() -> str:
    return """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no">
<title>SmartCore Screen</title>
<style>
:root {
  --bg: #0a0e14;
  --surface: #141b24;
  --text: #f0f4f8;
  --muted: #7a8a9a;
  --accent: #60a5fa;
  --connected: #4ade80;
  --offline: #f87171;
  --reminder-bg: #1e293b;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body {
  height: 100%;
  background: var(--bg);
  color: var(--text);
  font-family: "Segoe UI", system-ui, sans-serif;
  overflow: hidden;
}
.screen {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 1.25rem 1rem 1rem;
  max-width: 480px;
  margin: 0 auto;
}
.top-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
}
#wsStatus {
  display: flex;
  align-items: center;
  gap: .4rem;
  font-size: .75rem;
  color: var(--muted);
}
#wsStatus .dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--offline);
  transition: background .3s;
}
#wsStatus.connected .dot { background: var(--connected); }
#wsStatus.connected { color: var(--connected); }
.clock-wrap { text-align: center; flex: 0 0 auto; }
#clock {
  font-size: clamp(3rem, 14vw, 4.5rem);
  font-weight: 300;
  letter-spacing: .02em;
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
}
#clockDate {
  font-size: 1rem;
  color: var(--muted);
  margin-top: .35rem;
}
.state-wrap {
  text-align: center;
  margin: 1.5rem 0;
  flex: 0 0 auto;
}
.state-label {
  font-size: .7rem;
  text-transform: uppercase;
  letter-spacing: .12em;
  color: var(--muted);
  margin-bottom: .5rem;
}
#currentState {
  font-size: 1.75rem;
  font-weight: 600;
  padding: .6rem 1.2rem;
  border-radius: 999px;
  display: inline-block;
  background: var(--surface);
  min-width: 140px;
}
#currentState.working { background: #14532d; color: #86efac; }
#currentState.away { background: #713f12; color: #fde68a; }
#currentState.offline, #currentState.unknown { background: #374151; color: #d1d5db; }
.reminder-wrap {
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
  min-height: 0;
  margin-top: .5rem;
}
.reminder-label {
  font-size: .7rem;
  text-transform: uppercase;
  letter-spacing: .12em;
  color: var(--muted);
  margin-bottom: .5rem;
}
#reminderArea {
  flex: 1;
  background: var(--reminder-bg);
  border-radius: 12px;
  padding: 1rem;
  overflow-y: auto;
  border: 1px solid #2d3748;
}
#reminderArea.empty {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--muted);
  font-size: .95rem;
}
.reminder-card {
  background: var(--surface);
  border-radius: 10px;
  padding: .85rem 1rem;
  margin-bottom: .65rem;
  border-left: 3px solid var(--accent);
  animation: fadeIn .35s ease;
}
.reminder-card:last-child { margin-bottom: 0; }
.reminder-card .rem-title {
  font-weight: 600;
  font-size: 1rem;
  margin-bottom: .3rem;
}
.reminder-card .rem-content {
  font-size: .9rem;
  color: var(--muted);
  line-height: 1.45;
}
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
</head>
<body>
<div class="screen" id="screenRoot">
  <div class="top-bar">
    <span style="font-size:.85rem;font-weight:600;color:var(--muted)">SmartCore</span>
    <div id="wsStatus" data-ws-ui="status"><span class="dot"></span><span id="wsStatusText">连接中</span></div>
  </div>
  <div class="clock-wrap">
    <div id="clock" data-ws-ui="clock">--:--</div>
    <div id="clockDate">—</div>
  </div>
  <div class="state-wrap">
    <div class="state-label">当前状态</div>
    <div id="currentState" data-ws-ui="state" class="unknown">—</div>
  </div>
  <div class="reminder-wrap">
    <div class="reminder-label">提醒</div>
    <div id="reminderArea" data-ws-ui="reminder" class="empty">暂无提醒</div>
  </div>
</div>
<script>
(function () {
  const wsProto = location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${wsProto}//${location.host}/screen/ws`;
  let ws = null;
  let reconnectTimer = null;
  let serverOffsetMs = 0;
  let devState = "unknown";
  let hasReminders = false;

  const clockEl = document.getElementById("clock");
  const clockDateEl = document.getElementById("clockDate");
  const stateEl = document.getElementById("currentState");
  const reminderEl = document.getElementById("reminderArea");
  const wsStatusEl = document.getElementById("wsStatus");
  const wsStatusText = document.getElementById("wsStatusText");

  const weekdays = ["周日","周一","周二","周三","周四","周五","周六"];

  function setWsConnected(connected) {
    wsStatusEl.classList.toggle("connected", connected);
    wsStatusText.textContent = connected ? "已连接" : "离线";
  }

  function renderState() {
    stateEl.textContent = devState;
    stateEl.className = "";
    if (["working","away","offline","unknown"].includes(devState)) {
      stateEl.classList.add(devState);
    }
  }

  function tickClock() {
    const now = new Date(Date.now() + serverOffsetMs);
    const h = String(now.getHours()).padStart(2, "0");
    const m = String(now.getMinutes()).padStart(2, "0");
    clockEl.textContent = `${h}:${m}`;
    clockDateEl.textContent =
      `${now.getFullYear()}年${now.getMonth()+1}月${now.getDate()}日 ${weekdays[now.getDay()]}`;
  }

  function addReminder(title, content) {
    if (!hasReminders) {
      reminderEl.innerHTML = "";
      reminderEl.classList.remove("empty");
      hasReminders = true;
    }
    const card = document.createElement("div");
    card.className = "reminder-card";
    card.innerHTML =
      `<div class="rem-title"></div><div class="rem-content"></div>`;
    card.querySelector(".rem-title").textContent = title || "提醒";
    card.querySelector(".rem-content").textContent = content || "";
    reminderEl.prepend(card);
    while (reminderEl.children.length > 8) {
      reminderEl.removeChild(reminderEl.lastChild);
    }
  }

  function handleWsMessage(data) {
    if (data.kind === "state" && data.serverNow) {
      const serverMs = new Date(data.serverNow).getTime();
      serverOffsetMs = serverMs - Date.now();
      tickClock();
    } else if (data.kind === "devState" && data.state) {
      devState = data.state;
      renderState();
    } else if (data.kind === "reminder") {
      addReminder(data.title, data.content);
    }
  }

  function connectWs() {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
      return;
    }
    ws = new WebSocket(wsUrl);
    ws.onopen = () => setWsConnected(true);
    ws.onclose = () => {
      setWsConnected(false);
      reconnectTimer = setTimeout(connectWs, 3000);
    };
    ws.onerror = () => setWsConnected(false);
    ws.onmessage = (event) => {
      try {
        handleWsMessage(JSON.parse(event.data));
      } catch (_) { /* ignore non-json */ }
    };
  }

  tickClock();
  setInterval(tickClock, 1000);
  connectWs();
})();
</script>
</body>
</html>"""


@router.websocket("/screen/ws")
async def screenWebsocket(websocket: WebSocket, db: Session = Depends(get_db)) -> None:
    await screenManager.connect(websocket)
    dev = crud.getLatestDevState(db)
    if dev is not None:
        await websocket.send_json(
            {
                "kind": "devState",
                "state": dev["state"],
                "devId": dev["devId"],
                "seenAt": dev["seenAt"],
            }
        )
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await screenManager.disconnect(websocket)
