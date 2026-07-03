from __future__ import annotations

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import WebSocket

_DEFAULT_TZ = ZoneInfo("Asia/Shanghai")


class ScreenManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)
        await websocket.send_json(
            {
                "kind": "state",
                "serverNow": datetime.now(_DEFAULT_TZ).isoformat(),
            }
        )

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)

    async def broadcast(self, message: dict) -> None:
        async with self._lock:
            targets = list(self._connections)
        for websocket in targets:
            try:
                await websocket.send_json(message)
            except Exception:
                await self.disconnect(websocket)

    @property
    def online(self) -> bool:
        return bool(self._connections)


screenManager = ScreenManager()
