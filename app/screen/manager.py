from __future__ import annotations

import asyncio
import concurrent.futures
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

    async def broadcast(self, message: dict) -> None:
        async with self._lock:
            targets = list(self._connections)
        for websocket in targets:
            try:
                await websocket.send_json(message)
            except Exception:
                await self.disconnect(websocket)

    def broadcastFromThread(self, message: dict, *, timeout: float = 2.0) -> bool:
        if not self.online or self._loop is None:
            return False
        try:
            future = asyncio.run_coroutine_threadsafe(self.broadcast(message), self._loop)
            future.result(timeout=timeout)
        except (RuntimeError, concurrent.futures.TimeoutError):
            return False
        return True

    @property
    def online(self) -> bool:
        return bool(self._connections)


screenManager = ScreenManager()
