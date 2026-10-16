"""Short-lived, single-use WS tickets; long-lived credentials never enter URLs."""
from __future__ import annotations

import secrets
import time
from threading import Lock

from fastapi import HTTPException

from app.server.user_device.service import tokenHash


class ScreenTickets:
    def __init__(self):
        self._tickets: dict[str, tuple[float, str, str]] = {}
        self._lock = Lock()

    def issue(self, device_id: str, token_hash: str) -> str:
        now = time.monotonic()
        with self._lock:
            self._tickets = {key: value for key, value in self._tickets.items() if value[0] > now}
            if len(self._tickets) >= 4096:
                raise HTTPException(status_code=429, detail="too many pending connections")
            ticket = secrets.token_urlsafe(32)
            self._tickets[tokenHash(ticket)] = (now + 60, device_id, token_hash)
            return ticket

    def consume(self, ticket: str, device_id: str) -> str:
        with self._lock:
            value = self._tickets.pop(tokenHash(ticket), None)
        if value is None or value[0] <= time.monotonic() or value[1] != device_id:
            raise HTTPException(status_code=401, detail="invalid connection ticket")
        return value[2]


screenTickets = ScreenTickets()
