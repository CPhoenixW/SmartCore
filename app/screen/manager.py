from __future__ import annotations

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import WebSocket

_DEFAULT_TZ = ZoneInfo("Asia/Shanghai")


class ScreenManager:
    def __init__(self) -> None:
        self._connections: dict[WebSocket, str] = {}
        self._lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, websocket: WebSocket, userId: str) -> None:
        await websocket.accept()
        self._loop = asyncio.get_running_loop()
        async with self._lock:
            self._connections[websocket] = userId
        await websocket.send_json(
            {
                "kind": "state",
                "serverNow": datetime.now(_DEFAULT_TZ).isoformat(),
            }
        )

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.pop(websocket, None)

    async def broadcast(self, message: dict, *, userId: str | None = None) -> int:
        delivered = 0
        async with self._lock:
            targets = [websocket for websocket, owner in self._connections.items() if userId is None or owner == userId]
        for websocket in targets:
            try:
                await websocket.send_json(message)
                delivered += 1
            except Exception:
                await self.disconnect(websocket)
        return delivered

    def broadcastFromThread(self, message: dict, *, userId: str | None = None, timeout: float = 2.0) -> bool:
        if not self.online(userId) or self._loop is None:
            return False
        try:
            future = asyncio.run_coroutine_threadsafe(self.broadcast(message, userId=userId), self._loop)
            return future.result(timeout=timeout) > 0
        except Exception:
            return False

    @property
    def online(self, userId: str | None = None) -> bool:
        return any(owner == userId for owner in self._connections.values()) if userId else bool(self._connections)


screenManager = ScreenManager()
