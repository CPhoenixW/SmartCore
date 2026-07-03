from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.screen.manager import screenManager

router = APIRouter(tags=["screen"])


@router.get("/screen")
def screenPage() -> str:
    return """<!doctype html>
<html><head><meta charset="utf-8"><title>SmartCore Screen</title></head>
<body><h1>SmartCore 副屏</h1><div id="state"></div>
<script>
const ws = new WebSocket(`ws://${location.host}/screen/ws`);
ws.onmessage = (event) => {
  document.getElementById('state').textContent = event.data;
};
</script></body></html>"""


@router.websocket("/screen/ws")
async def screenWebsocket(websocket: WebSocket) -> None:
    await screenManager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await screenManager.disconnect(websocket)
