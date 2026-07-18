#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
LOG_PATH = Path(os.environ.get("ADAPTER_LOG_PATH", str(BASE_DIR / "adapter.log")))
MAX_FINAL_TEXT = 800
MAX_STDERR = 800


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def log(log_message: str, **fields: Any) -> None:
    record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "message": log_message, **fields}
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def safe_session_part(value: str) -> str:
    value = value.strip() or "unknown"
    return re.sub(r"[^A-Za-z0-9_.:-]+", "-", value)[:120]


def compact(value: Any, limit: int) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[:limit] + "..."


def sanitize_event(event: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {
        "event_id": event.get("event_id"),
        "source": event.get("source"),
        "event_type": event.get("event_type") or event.get("eventType"),
    }
    for key in ("chat_id", "message_id", "text", "userId", "sourceBindId"):
        if event.get(key) is not None:
            sanitized[key] = event.get(key)
    for key in ("request", "chat", "user"):
        if isinstance(event.get(key), dict):
            sanitized[key] = event[key]

    message = event.get("message")
    if isinstance(message, dict):
        sanitized["message"] = {
            key: message.get(key)
            for key in ("message_id", "text")
            if message.get(key) is not None
        }

    card_action = event.get("card_action")
    if isinstance(card_action, dict):
        action = card_action.get("action") if isinstance(card_action.get("action"), dict) else {}
        context = card_action.get("context") if isinstance(card_action.get("context"), dict) else {}
        sanitized["card_action"] = {
            "value": action.get("value") if isinstance(action, dict) else None,
            "tag": action.get("tag") if isinstance(action, dict) else None,
            "context": {
                key: context.get(key)
                for key in ("open_chat_id", "open_message_id")
                if context.get(key) is not None
            },
        }
    return sanitized


def build_prompt(event: dict[str, Any]) -> str:
    base_url = os.environ.get("SMARTCORE_BASE_URL", "http://127.0.0.1:8000")
    token_file = os.environ.get(
        "SMARTCORE_AGENT_TOKEN_FILE",
        "/root/.openclaw/smartcore-agent-api-token",
    )
    chat = event.get("chat") if isinstance(event.get("chat"), dict) else {}
    user = event.get("user") if isinstance(event.get("user"), dict) else {}
    reply_chat_id = event.get("chat_id") or chat.get("chat_id")
    scope = str(event.get("agentScope") or "").strip()
    return (
        "You are SmartCore Agent handling one forwarded Feishu event.\n"
        "Do not run onboarding, identity setup, or general assistant bootstrap flows.\n"
        "Use SmartCore Agent APIs and Feedback APIs for all data operations and Feishu replies.\n"
        "Do not access SQLite files, Docker volumes, backups, or SmartCore internals directly.\n"
        f"SmartCore base URL: {base_url}\n"
        f"Read the SmartCore API token from {token_file} only inside the command that calls SmartCore. Never print it.\n"
        "Required SmartCore header name: X-SmartCore-Agent-Token.\n"
        f"For EVERY /agent database or feedback request, also send X-SmartCore-Agent-Scope: {scope}\n"
        "For relative time queries, calculate explicit ISO-8601 start/end ranges from event.request.now and event.request.timezone.\n"
        "Every handled event must end with a Feishu reply through the scoped /agent/feedback endpoints.\n"
        "On success, send a short confirmation. On failure or ambiguity, send one concise clarification or error message.\n"
        "Do not pass chat_id, receiveId, openId, or userId to feedback APIs: the signed scope is the only routing authority.\n"
        f"Bound reply chat_id: {reply_chat_id or 'missing'}\n"
        f"User routing context: {json.dumps(user, ensure_ascii=False) if user else '{}'}\n"
        "If the target is ambiguous, send a concise clarification through SmartCore feedback instead of guessing.\n"
        "Forwarded compact event JSON follows:\n"
        f"{json.dumps(sanitize_event(event), ensure_ascii=False, indent=2)}"
    )


def find_key(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        if key in value:
            return value[key]
        for child in value.values():
            found = find_key(child, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_key(child, key)
            if found is not None:
                return found
    return None


def summarize_openclaw(stdout: str, stderr: str) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    try:
        payload = json.loads(stdout)
    except Exception:
        summary["stdout_tail"] = compact(stdout[-1000:], 1000)
        summary["stderr_tail"] = compact(stderr[-MAX_STDERR:], MAX_STDERR)
        return summary

    summary["final_text"] = compact(find_key(payload, "finalAssistantVisibleText"), MAX_FINAL_TEXT)
    summary["tool_summary"] = find_key(payload, "toolSummary")
    trace = find_key(payload, "executionTrace")
    if isinstance(trace, dict):
        summary["provider"] = trace.get("winnerProvider")
        summary["model"] = trace.get("winnerModel")
        summary["fallback_used"] = trace.get("fallbackUsed")
    shaping = find_key(payload, "requestShaping")
    if isinstance(shaping, dict):
        summary["thinking"] = shaping.get("thinking")
    if stderr:
        summary["stderr_tail"] = compact(stderr[-MAX_STDERR:], MAX_STDERR)
    return summary


def run_openclaw(event: dict[str, Any]) -> None:
    started = time.monotonic()
    chat = event.get("chat") if isinstance(event.get("chat"), dict) else {}
    user = event.get("user") if isinstance(event.get("user"), dict) else {}
    target = event.get("chat_id") or chat.get("chat_id") or user.get("user_id") or event.get("event_id") or "unknown"
    agent_id = os.environ.get("OPENCLAW_AGENT_ID", "smartcore")
    session_prefix = os.environ.get("OPENCLAW_SESSION_PREFIX", f"agent:{agent_id}:smartcore-feishu")
    session_key = f"{session_prefix}-{safe_session_part(str(target))}"
    workspace = os.environ.get("OPENCLAW_WORKSPACE", "/root/.openclaw-smartcore-workspace")
    cmd = [
        os.environ.get("OPENCLAW_BIN", "/root/.openclaw/bin/openclaw"),
        "agent",
        "--agent", agent_id,
        "--session-key", session_key,
        "--thinking", os.environ.get("OPENCLAW_THINKING", "low"),
        "--message", build_prompt(event),
        "--json",
    ]
    env = os.environ.copy()
    env["PATH"] = f"/root/.openclaw/bin:{env.get('PATH', '')}"
    try:
        result = subprocess.run(
            cmd,
            env=env,
            cwd=workspace,
            text=True,
            capture_output=True,
            timeout=int(os.environ.get("OPENCLAW_TIMEOUT_SECONDS", "600")),
        )
        duration_ms = int((time.monotonic() - started) * 1000)
        log(
            "openclaw finished",
            event_id=event.get("event_id"),
            returncode=result.returncode,
            duration_ms=duration_ms,
            **summarize_openclaw(result.stdout, result.stderr),
        )
    except Exception as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        log("openclaw failed", event_id=event.get("event_id"), duration_ms=duration_ms, error=repr(exc))


class Handler(BaseHTTPRequestHandler):
    server_version = "SmartCoreOpenClawAdapter/0.3"

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._json(200, {"ok": True})
            return
        self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/api/smartcore/events":
            self._json(404, {"ok": False, "error": "not found"})
            return
        expected = os.environ.get("OPENCLAW_EVENTS_TOKEN", "")
        auth = self.headers.get("Authorization", "")
        if expected and auth != f"Bearer {expected}":
            self._json(401, {"ok": False, "error": "unauthorized"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            event = json.loads(body.decode("utf-8"))
            if not isinstance(event, dict):
                raise ValueError("event body must be an object")
        except Exception as exc:
            self._json(400, {"ok": False, "error": str(exc)})
            return
        threading.Thread(target=run_openclaw, args=(event,), daemon=True).start()
        log("event accepted", event=sanitize_event(event))
        self._json(202, {"ok": True, "status": "accepted"})

    def log_message(self, fmt: str, *args: Any) -> None:
        log("http", client=self.client_address[0], detail=fmt % args)


def main() -> None:
    load_env(BASE_DIR / ".env")
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "18790"))
    server = ThreadingHTTPServer((host, port), Handler)
    log(
        "adapter started",
        host=host,
        port=port,
        agent=os.environ.get("OPENCLAW_AGENT_ID", "smartcore"),
        thinking=os.environ.get("OPENCLAW_THINKING", "low"),
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
