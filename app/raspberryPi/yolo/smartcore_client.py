#!/usr/bin/env python3
"""Post device state to SmartCore using urllib (stdlib only)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ENV_PATH = Path(__file__).resolve().parent / ".smartcore.env"
TOKEN_HEADER = "X-SmartCore-Device-Token"


def loadSmartcoreEnv(path: Path | None = None) -> dict[str, str]:
    env_path = path or ENV_PATH
    values: dict[str, str] = {}
    if not env_path.is_file():
        return values
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def mapDetectionStatus(rawStatus: str) -> tuple[str, dict[str, Any]]:
    meta: dict[str, Any] = {"rawStatus": rawStatus}
    if rawStatus.startswith("working:"):
        parts = rawStatus.split(":", 2)
        if len(parts) >= 2:
            meta["identity"] = parts[1]
        if len(parts) >= 3:
            meta["detail"] = parts[2]
        return "working", meta
    if rawStatus == "absent":
        return "away", meta
    return "offline", meta


def postDevState(
    rawStatus: str,
    *,
    confidence: float | None = None,
    env: dict[str, str] | None = None,
) -> bool:
    cfg = env or loadSmartcoreEnv()
    base_url = cfg.get("SMARTCORE_BASE_URL", "").rstrip("/")
    dev_id = cfg.get("SMARTCORE_DEV_ID", "pi")
    token = cfg.get("SMARTCORE_DEVICE_TOKEN", "")
    timeout = float(cfg.get("SMARTCORE_POST_TIMEOUT", "5"))

    if not base_url:
        return False

    state, meta = mapDetectionStatus(rawStatus)
    payload = {
        "devId": dev_id,
        "state": state,
        "confidence": confidence,
        "meta": meta,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/dev/state",
        data=data,
        headers={
            "Content-Type": "application/json",
            TOKEN_HEADER: token,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except urllib.error.URLError:
        return False
