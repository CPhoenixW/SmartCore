"""Browser origin checks and bounded limits for a single-worker deployment."""
from __future__ import annotations

import ipaddress
import re
import time
from collections import deque
from threading import Lock

from fastapi import Request
from fastapi.responses import JSONResponse

from app.server.config import Settings

_PAIR_CLIENT = re.compile(r"^/api/device/pair/[^/]+/(claim|activate|status)$")
_DEVICE_PATHS = {
    "/api/device/dispatch", "/api/device/receipt",
    "/api/computer/activity/batch", "/api/computer/heartbeat",
    "/api/computer/codex-reports/batch",
}


def machine_request(path: str, method: str) -> bool:
    return bool(
        _PAIR_CLIENT.fullmatch(path)
        or path.startswith("/dev/") or path.startswith("/screen/")
        or (path in _DEVICE_PATHS and not (path == "/api/device/dispatch" and method == "POST"))
    )


def client_ip(request: Request, networks: str) -> str:
    peer = request.client.host if request.client else "unknown"
    try:
        address = ipaddress.ip_address(peer)
        trusted = any(address in ipaddress.ip_network(item.strip()) for item in networks.split(",") if item.strip())
        if trusted:
            return str(ipaddress.ip_address(request.headers.get("x-smartcore-client-ip", peer)))
    except ValueError:
        pass
    return peer


class RequestLimits:
    def __init__(self, *, capacity: int = 4096):
        self.capacity = capacity
        self._buckets: dict[tuple[str, str], deque[float]] = {}
        self._lock = Lock()

    def allow(self, group: str, identity: str, limit: int, seconds: int) -> bool:
        now = time.monotonic()
        with self._lock:
            # Every group uses the same 60-second window, keeping memory bounded.
            for key in list(self._buckets):
                bucket = self._buckets[key]
                while bucket and bucket[0] <= now - seconds:
                    bucket.popleft()
                if not bucket:
                    del self._buckets[key]
            key = (group, identity)
            if key not in self._buckets:
                if len(self._buckets) >= self.capacity:
                    return False
                self._buckets[key] = deque()
            bucket = self._buckets[key]
            if len(bucket) >= limit:
                return False
            bucket.append(now)
            return True


def reject_request(request: Request, settings: Settings, limits: RequestLimits) -> JSONResponse | None:
    path, method = request.url.path, request.method
    if method not in {"GET", "HEAD", "OPTIONS"} and path.startswith("/api/") and not machine_request(path, method):
        origin = request.headers.get("origin")
        expected = settings.public_origin if settings.public_access_enabled else str(request.base_url).rstrip("/")
        if (origin is not None and origin != expected) or (settings.public_access_enabled and origin is None):
            return JSONResponse({"detail": "same-origin browser request required"}, status_code=403)
    group, limit = "", 0
    if path in {"/api/auth/login", "/api/auth/register", "/api/auth/setup", "/api/auth/password"} and method == "POST":
        group, limit = "authentication", 10
    elif _PAIR_CLIENT.fullmatch(path):
        group, limit = "pairing", 120
    elif path == "/screen/ws-ticket":
        group, limit = "screen-connect", 30
    if group and not limits.allow(group, client_ip(request, settings.trusted_proxy_networks), limit, 60):
        return JSONResponse({"detail": "too many requests"}, status_code=429, headers={"Retry-After": "60"})
    return None
