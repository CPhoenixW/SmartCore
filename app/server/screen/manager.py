from __future__ import annotations

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import WebSocket
from sqlalchemy import select

from app.server.db.session import SessionLocal
from app.server.new_core.models import AppUser, DeviceKey, LifeDevice

_DEFAULT_TZ = ZoneInfo("Asia/Shanghai")


class ScreenManager:
    def __init__(self) -> None:
        self._connections: dict[WebSocket, tuple[str, str, str]] = {}
        self._lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, websocket: WebSocket, userId: str, deviceId: str, tokenHash: str) -> None:
        await websocket.accept()
        self._loop = asyncio.get_running_loop()
        async with self._lock:
            self._connections[websocket] = (userId, deviceId, tokenHash)
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
        if userId is None:
            raise ValueError("screen broadcasts require an owner")
        delivered = 0
        async with self._lock:
            targets = [websocket for websocket, context in self._connections.items() if context[0] == userId]
        for websocket in targets:
            try:
                if not await self.authorize(websocket):
                    continue
                await websocket.send_json(message)
                delivered += 1
            except Exception:
                await self.disconnect(websocket)
        return delivered

    async def authorize(self, websocket: WebSocket) -> bool:
        context = self._connections.get(websocket)
        if context and credential_active(*context):
            return True
        await self.disconnect(websocket)
        await websocket.close(code=1008)
        return False

    def broadcastFromThread(self, message: dict, *, userId: str | None = None, timeout: float = 2.0) -> bool:
        if not self.online(userId) or self._loop is None:
            return False
        try:
            future = asyncio.run_coroutine_threadsafe(self.broadcast(message, userId=userId), self._loop)
            return future.result(timeout=timeout) > 0
        except Exception:
            return False

    def online(self, userId: str | None = None) -> bool:
        return any(context[0] == userId for context in self._connections.values()) if userId else bool(self._connections)


def credential_active(user_id: str, device_id: str, token_hash: str) -> bool:
    with SessionLocal() as db:
        return db.scalar(
            select(DeviceKey.keyId).join(LifeDevice, LifeDevice.deviceId == DeviceKey.deviceId)
            .join(AppUser, AppUser.userId == LifeDevice.userId)
            .where(DeviceKey.tokenHash == token_hash, DeviceKey.revokedAt.is_(None),
                   LifeDevice.deviceId == device_id, LifeDevice.userId == user_id,
                   LifeDevice.deviceKind == "screen", LifeDevice.stat == "active", AppUser.stat == "active")
        ) is not None


screenManager = ScreenManager()
