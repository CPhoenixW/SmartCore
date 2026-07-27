#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import urllib.parse
from collections.abc import Sequence
from pathlib import Path
from typing import Any


def runtime_config() -> dict[str, str]:
    path = Path(__file__).resolve().parents[1] / "runtime.json"
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {
        key: item
        for key, item in value.items()
        if key in {"base_url", "token_file"} and isinstance(item, str) and item
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Call one scoped SmartCore Agent tool.")
    result.add_argument("--scope-file", required=True)
    result.add_argument("--tool", required=True)
    result.add_argument("--body-json", default="{}")
    return result


def _request_json(request: urllib.request.Request, *, timeout: int = 20) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"SmartCore HTTP {exc.code}: {detail[:500]}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("SmartCore returned a non-object response")
    return payload


def _resolve_tool(tools: list[Any], requested_name: str) -> dict[str, Any] | None:
    published = [item for item in tools if isinstance(item, dict)]
    exact = next((item for item in published if item.get("name") == requested_name), None)
    if exact is not None:
        return exact

    # Models sometimes use the final path component shown in the published contract
    # (for example ``update_event``) instead of its tool name (``evtUpdate``).
    # Resolve that spelling only when it identifies exactly one published tool, so
    # compatibility never grants access to an unpublished endpoint.
    path_matches = [
        item
        for item in published
        if str(item.get("path") or "").rstrip("/").rsplit("/", 1)[-1] == requested_name
    ]
    return path_matches[0] if len(path_matches) == 1 else None


def call_tool(args: argparse.Namespace) -> dict[str, Any]:
    runtime = runtime_config()
    scope = Path(args.scope_file).read_text(encoding="utf-8").strip()
    if not scope:
        raise ValueError("SmartCore agent scope is unavailable")
    token_file = Path(
        os.environ.get(
            "SMARTCORE_AGENT_TOKEN_FILE",
            runtime.get("token_file", "/root/.openclaw/smartcore-agent-api-token"),
        )
    )
    token = token_file.read_text(encoding="utf-8").strip()
    if not token:
        raise ValueError("SmartCore agent token is unavailable")
    base_url = os.environ.get(
        "SMARTCORE_BASE_URL",
        runtime.get("base_url", "http://127.0.0.1:8000"),
    ).rstrip("/")
    headers = {
        "X-SmartCore-Agent-Token": token,
        "X-SmartCore-Agent-Scope": scope,
    }
    catalog = _request_json(
        urllib.request.Request(f"{base_url}/agent/tools", headers=headers)
    )
    data = catalog.get("data") if isinstance(catalog.get("data"), dict) else {}
    tools = data.get("tools") if isinstance(data.get("tools"), list) else []
    tool = _resolve_tool(tools, args.tool)
    if tool is None:
        raise ValueError(f"SmartCore tool is unavailable: {args.tool}")
    method = str(tool.get("method") or "POST").upper()
    path = str(tool.get("path") or "")
    if method not in {"GET", "POST"} or not path.startswith("/agent/"):
        raise ValueError(f"SmartCore tool has an unsupported contract: {args.tool}")
    body = json.loads(args.body_json)
    if not isinstance(body, dict):
        raise ValueError("--body-json must contain a JSON object")
    if method == "GET":
        query = urllib.parse.urlencode({key: value for key, value in body.items() if value is not None})
        request = urllib.request.Request(f"{base_url}{path}?{query}", headers=headers, method="GET")
    else:
        request = urllib.request.Request(
            f"{base_url}{path}",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={**headers, "Content-Type": "application/json"},
            method="POST",
        )
    return _request_json(request)


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result = call_tool(args)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
