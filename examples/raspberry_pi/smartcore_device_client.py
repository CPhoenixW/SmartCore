from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
from zoneinfo import ZoneInfo

import httpx

_TZ = ZoneInfo("Asia/Shanghai")
_LOG = logging.getLogger("smartcore-pi")


class RecognitionProvider(Protocol):
    """Adapter implemented by the existing camera / YOLO process."""

    def latest_jpeg(self) -> bytes:
        """Return the latest frame encoded as JPEG."""

    def latest_result(self) -> dict[str, Any]:
        """Return present/persons/stateConfidence/state/meta."""


class SnapshotLogger:
    def __init__(self, root: Path, retention_hours: int = 24) -> None:
        self.root = root
        self.retention_seconds = retention_hours * 3600
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def save(self, jpeg: bytes, result: dict[str, Any], captured_at: datetime) -> None:
        folder = self.root / captured_at.strftime("%Y-%m-%d") / captured_at.strftime("%H")
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        stem = captured_at.strftime("%Y%m%dT%H%M%S%z")
        image_path = folder / f"{stem}.jpg"
        json_path = folder / f"{stem}.json"
        payload = {
            "capturedAt": captured_at.isoformat(),
            "present": bool(result.get("present", False)),
            "persons": result.get("persons") or [],
            "state": result.get("state"),
            "stateConfidence": float(result.get("stateConfidence", 0.0)),
            "meta": result.get("meta") or {},
        }
        self._atomic_write(image_path, jpeg)
        self._atomic_write(
            json_path,
            json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
        )

    def cleanup(self) -> None:
        cutoff = time.time() - self.retention_seconds
        files = sorted((path for path in self.root.rglob("*") if path.is_file()), reverse=True)
        for path in files:
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)
            except FileNotFoundError:
                continue
        directories = sorted(
            (path for path in self.root.rglob("*") if path.is_dir()),
            key=lambda item: len(item.parts),
            reverse=True,
        )
        for folder in directories:
            try:
                folder.rmdir()
            except OSError:
                pass

    @staticmethod
    def _atomic_write(path: Path, content: bytes) -> None:
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


class SmartCoreDeviceClient:
    def __init__(
        self,
        provider: RecognitionProvider,
        *,
        server: str,
        device_id: str,
        token: str,
        log_dir: Path,
        heartbeat_seconds: int = 10,
        snapshot_seconds: int = 60,
        retention_hours: int = 24,
    ) -> None:
        self.provider = provider
        self.server = server.rstrip("/")
        self.device_id = device_id
        self.heartbeat_seconds = heartbeat_seconds
        self.snapshot_seconds = snapshot_seconds
        self.logger = SnapshotLogger(log_dir, retention_hours)
        self.http = httpx.Client(
            headers={"X-SmartCore-Device-Token": token},
            timeout=httpx.Timeout(5.0, connect=3.0),
        )
        self.completed_request_ids: set[str] = set()

    def run(self) -> None:
        next_heartbeat = time.monotonic()
        next_snapshot = time.monotonic()
        next_cleanup = time.monotonic()
        backoff = 0

        while True:
            now_mono = time.monotonic()
            if now_mono >= next_snapshot:
                self._save_local_snapshot()
                next_snapshot = self._advance(next_snapshot, self.snapshot_seconds, now_mono)

            if now_mono >= next_cleanup:
                self.logger.cleanup()
                next_cleanup = self._advance(next_cleanup, 600, now_mono)

            if now_mono >= next_heartbeat:
                try:
                    request = self._heartbeat()
                    backoff = 0
                    if request:
                        self._upload_photo_request(request)
                    next_heartbeat = self._advance(
                        next_heartbeat,
                        self.heartbeat_seconds,
                        now_mono,
                    )
                except Exception:
                    _LOG.exception("heartbeat/photo cycle failed")
                    backoff = min(60, 2 if backoff == 0 else max(5, backoff * 2))
                    next_heartbeat = time.monotonic() + backoff

            time.sleep(0.2)

    def _heartbeat(self) -> dict[str, Any] | None:
        result = self.provider.latest_result()
        now = datetime.now(_TZ)
        payload = {
            "devId": self.device_id,
            "currentTime": now.isoformat(),
            "present": bool(result.get("present", False)),
            "persons": result.get("persons") or [],
            "stateConfidence": float(result.get("stateConfidence", 0.0)),
            "state": result.get("state"),
            "meta": result.get("meta") or {},
        }
        response = self.http.post(f"{self.server}/dev/heartbeat", json=payload)
        response.raise_for_status()
        body = response.json()
        if not body.get("ok"):
            raise RuntimeError(f"heartbeat rejected: {body}")
        data = body.get("data") or {}
        request = data.get("photoRequest")
        if isinstance(request, dict):
            return request
        return None

    def _upload_photo_request(self, request: dict[str, Any]) -> None:
        request_id = str(request.get("requestId") or "")
        if not request_id or request_id in self.completed_request_ids:
            return
        captured_at = datetime.now(_TZ)
        result = self.provider.latest_result()
        jpeg = self.provider.latest_jpeg()
        files = {"image": ("current.jpg", jpeg, "image/jpeg")}
        data = {
            "devId": self.device_id,
            "capturedAt": captured_at.isoformat(),
            "recognition": json.dumps(result, ensure_ascii=False),
        }
        response = self.http.post(
            f"{self.server}/dev/photo/{request_id}",
            data=data,
            files=files,
            timeout=15.0,
        )
        response.raise_for_status()
        body = response.json()
        if not body.get("ok"):
            raise RuntimeError(f"photo upload rejected: {body}")
        self.completed_request_ids.add(request_id)
        if len(self.completed_request_ids) > 200:
            self.completed_request_ids = set(list(self.completed_request_ids)[-100:])

    def _save_local_snapshot(self) -> None:
        captured_at = datetime.now(_TZ)
        self.logger.save(
            self.provider.latest_jpeg(),
            self.provider.latest_result(),
            captured_at,
        )

    @staticmethod
    def _advance(previous: float, interval: int, now: float) -> float:
        candidate = previous + interval
        if candidate <= now:
            return now + interval
        return candidate


def client_from_environment(provider: RecognitionProvider) -> SmartCoreDeviceClient:
    return SmartCoreDeviceClient(
        provider,
        server=os.environ["SMARTCORE_SERVER"],
        device_id=os.getenv("SMARTCORE_DEVICE_ID", "pi"),
        token=os.environ["SMARTCORE_DEVICE_TOKEN"],
        log_dir=Path(os.getenv("SMARTCORE_LOG_DIR", "/var/lib/smartcore-pi/logs")),
        heartbeat_seconds=int(os.getenv("SMARTCORE_HEARTBEAT_SECONDS", "10")),
        snapshot_seconds=int(os.getenv("SMARTCORE_SNAPSHOT_SECONDS", "60")),
        retention_hours=int(os.getenv("SMARTCORE_RETENTION_HOURS", "24")),
    )
