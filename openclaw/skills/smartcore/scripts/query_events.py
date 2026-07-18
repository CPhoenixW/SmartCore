#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Sequence


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
    result = argparse.ArgumentParser(description="Query scoped SmartCore events.")
    result.add_argument("--scope", required=True)
    result.add_argument("--date")
    result.add_argument("--start")
    result.add_argument("--end")
    result.add_argument("--event-id")
    result.add_argument("--event-type", action="append")
    result.add_argument("--status", action="append")
    result.add_argument("--text")
    result.add_argument("--include-reminders", action="store_true")
    result.add_argument("--include-course-templates", action="store_true")
    result.add_argument("--limit", type=int, default=100)
    return result


def build_body(args: argparse.Namespace) -> dict[str, Any]:
    if args.date and (args.start or args.end):
        raise ValueError("--date cannot be combined with --start/--end")
    if bool(args.start) != bool(args.end):
        raise ValueError("--start and --end must be provided together")
    if not 1 <= args.limit <= 500:
        raise ValueError("--limit must be between 1 and 500")

    body: dict[str, Any] = {
        "includeLinkedPlans": True,
        "includeCourseTemplates": bool(args.include_course_templates),
        "includeReminders": bool(args.include_reminders),
        "limit": args.limit,
    }
    if args.date:
        body["date"] = args.date
    if args.start and args.end:
        body["timeRange"] = {"start": args.start, "end": args.end}
    if args.event_id:
        body["evtId"] = args.event_id
    if args.event_type:
        body["evtTypes"] = args.event_type
    if args.status:
        body["stats"] = args.status
    if args.text:
        body["text"] = args.text
    return body


def query_events(args: argparse.Namespace) -> dict[str, Any]:
    runtime = runtime_config()
    token_file = Path(
        os.environ.get(
            "SMARTCORE_AGENT_TOKEN_FILE",
            runtime.get("token_file", "/root/.openclaw/smartcore-agent-api-token"),
        )
    )
    token = token_file.read_text(encoding="utf-8").strip()
    if not token:
        raise ValueError("SmartCore agent token is empty")
    base_url = os.environ.get(
        "SMARTCORE_BASE_URL",
        runtime.get("base_url", "http://127.0.0.1:8000"),
    ).rstrip("/")
    request = urllib.request.Request(
        f"{base_url}/agent/db/query_events",
        data=json.dumps(build_body(args), ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-SmartCore-Agent-Token": token,
            "X-SmartCore-Agent-Scope": args.scope,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"SmartCore query HTTP {exc.code}: {detail[:500]}") from exc


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result = query_events(args)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False))
    if not isinstance(result, dict) or result.get("ok") is not True:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
