#!/usr/bin/env python3
"""Quick SmartCore connectivity and /dev/state post test."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from smartcore_client import loadSmartcoreEnv, postDevState

ENV_PATH = Path(__file__).resolve().parent / ".smartcore.env"


def pingHealth(base_url: str, timeout: float) -> tuple[bool, str]:
    url = f"{base_url.rstrip('/')}/healthz"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return resp.status == 200, body
    except urllib.error.URLError as exc:
        return False, str(exc)


def main() -> int:
    cfg = loadSmartcoreEnv(ENV_PATH)
    base_url = cfg.get("SMARTCORE_BASE_URL", "")
    timeout = float(cfg.get("SMARTCORE_POST_TIMEOUT", "5"))

    if not base_url:
        print("SMARTCORE_BASE_URL missing in .smartcore.env", file=sys.stderr)
        return 1

    ok, detail = pingHealth(base_url, timeout)
    print(f"healthz: {'ok' if ok else 'fail'} {detail}")

    posted = postDevState("working:test", confidence=0.5, env=cfg)
    print(f"dev/state test post: {'ok' if posted else 'fail'}")
    return 0 if ok and posted else 2


if __name__ == "__main__":
    raise SystemExit(main())
