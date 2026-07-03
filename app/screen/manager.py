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
        self._loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._loop = asyncio.get_running_loop()
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

    async def broadcast(self, message: dict) -> int:
        delivered = 0
        async with self._lock:
            targets = list(self._connections)
        for websocket in targets:
            try:
                await websocket.send_json(message)
                delivered += 1
            except Exception:
                await self.disconnect(websocket)
        return delivered

    def broadcastFromThread(self, message: dict, *, timeout: float = 2.0) -> bool:
        if not self.online or self._loop is None:
            return False
        try:
            future = asyncio.run_coroutine_threadsafe(self.broadcast(message), self._loop)
            return future.result(timeout=timeout) > 0
        except Exception:
            return False

    @property
    def online(self) -> bool:
        return bool(self._connections)


screenManager = ScreenManager()
