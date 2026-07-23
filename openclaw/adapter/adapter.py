#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
LOG_PATH = Path(os.environ.get("ADAPTER_LOG_PATH", str(BASE_DIR / "adapter.log")))
MAX_FINAL_TEXT = 800
MAX_STDERR = 800
FAILURE_REPLY = "抱歉，这次处理没有成功，请稍后再试。"
DAILY_HEADINGS = (
    "### 📝 本日工作概述",
    "### 🚀 今日主要成果与技术进展",
    "### ⚠️ 遇到问题与阻碍 (Blockers)",
    "### 📅 明日规划",
)


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def sync_bundled_skill() -> bool:
    skill_file = Path(
        os.environ.get(
            "SMARTCORE_BUNDLED_SKILL",
            "/adapter/skills/smartcore/SKILL.md",
        )
    )
    if not skill_file.is_file():
        return False
    workspace = Path(
        os.environ.get(
            "OPENCLAW_WORKSPACE",
            "/root/.openclaw-smartcore-workspace",
        )
    )
    source_root = skill_file.parent
    target_root = workspace / "skills" / "smartcore"
    changed = False
    for source in sorted(path for path in source_root.rglob("*") if path.is_file()):
        target = target_root / source.relative_to(source_root)
        content = source.read_bytes()
        if target.is_file() and target.read_bytes() == content:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.tmp")
        temporary.write_bytes(content)
        temporary.chmod(0o700 if source.suffix == ".py" else 0o600)
        temporary.replace(target)
        changed = True
    return changed


def bundled_skill_ready() -> bool:
    skill_file = Path(
        os.environ.get("SMARTCORE_BUNDLED_SKILL", "/adapter/skills/smartcore/SKILL.md")
    )
    workspace = Path(
        os.environ.get("OPENCLAW_WORKSPACE", "/root/.openclaw-smartcore-workspace")
    )
    target = workspace / "skills" / "smartcore" / "SKILL.md"
    return bool(
        skill_file.is_file()
        and target.is_file()
        and target.read_bytes() == skill_file.read_bytes()
    )


def write_skill_runtime_config() -> bool:
    workspace = Path(
        os.environ.get(
            "OPENCLAW_WORKSPACE",
            "/root/.openclaw-smartcore-workspace",
        )
    )
    target = workspace / "skills" / "smartcore" / "runtime.json"
    content = (
        json.dumps(
            {
                "base_url": os.environ.get("SMARTCORE_BASE_URL", "http://127.0.0.1:8000"),
                "token_file": os.environ.get(
                    "SMARTCORE_AGENT_TOKEN_FILE",
                    "/root/.openclaw/smartcore-agent-api-token",
                ),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    if target.is_file() and target.read_bytes() == content:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_bytes(content)
    temporary.chmod(0o600)
    temporary.replace(target)
    return True


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


def openclaw_node_bin() -> str:
    configured = os.environ.get("OPENCLAW_NODE_BIN", "").strip()
    if configured:
        return configured
    candidates = sorted(Path("/root/.openclaw/tools").glob("node-*/bin"), reverse=True)
    return str(candidates[0]) if candidates else ""


def sanitize_event(event: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {
        "event_id": event.get("event_id"),
        "source": event.get("source"),
        "event_type": event.get("event_type") or event.get("eventType"),
    }
    for key in (
        "chat_id",
        "message_id",
        "text",
        "userId",
        "sourceBindId",
        "reportDate",
        "jobId",
        "targetIdeaId",
    ):
        if event.get(key) is not None:
            sanitized[key] = event.get(key)
    for key in ("request", "chat", "user"):
        if isinstance(event.get(key), dict):
            sanitized[key] = event[key]

    message = event.get("message")
    if isinstance(message, dict):
        sanitized["message"] = {
            key: message.get(key)
            for key in ("message_id", "text", "attachments")
            if message.get(key) is not None
        }
    if isinstance(event.get("attachments"), list):
        sanitized["attachments"] = event["attachments"]

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


def build_prompt(event: dict[str, Any], *, scope_file: str | None = None) -> str:
    base_url = os.environ.get("SMARTCORE_BASE_URL", "http://127.0.0.1:8000")
    token_file = os.environ.get(
        "SMARTCORE_AGENT_TOKEN_FILE",
        "/root/.openclaw/smartcore-agent-api-token",
    )
    chat = event.get("chat") if isinstance(event.get("chat"), dict) else {}
    user = event.get("user") if isinstance(event.get("user"), dict) else {}
    reply_chat_id = event.get("chat_id") or chat.get("chat_id")
    scope_instruction = (
        f'Before the first such command, run: export SMARTCORE_AGENT_SCOPE="$(cat {scope_file})". '
        "The task scope file is the only authorized source; never print, copy, or paste its value.\n"
        if scope_file
        else "The task scope is unavailable; do not attempt SmartCore API calls.\n"
    )
    auth_instructions = (
        "For EVERY /agent database or feedback request, send X-SmartCore-Agent-Scope. "
        + scope_instruction
    )
    daily_summary_instructions = ""
    if event.get("event_type") == "daily_summary":
        report_date = str(event.get("reportDate") or "").strip()
        daily_summary_instructions = (
            "这是定时日报任务。最终答案必须是中文成品，且只能包含日报本身。\n"
            f"日报日期：{report_date}\n"
            "禁止输出分析过程、筛选清单、工具说明、英文前言、事件原始行或 ID。\n"
            "只能引用本次查询所得标题、状态和描述；禁止沿用其他日期或会话中的项目、阻碍和计划。\n"
            "过滤通勤、打卡、出发、交通、抢票等无工作产出的生活事项。\n"
            "同一事项若 DDL 为 cancelled 且关联 plan 为 done，只汇报已完成的业务事项，不汇报 DDL 取消。\n"
            "按项目/模块归纳成果，不按时间流水账排列。不要在标题中罗列时间段。\n"
            "完成事项只从描述提取脚本、命令、版本、封装功能和踩坑；记录缺失时写“记录中未提供技术细节”，严禁猜测。\n"
            "未完成事项提炼明确阻碍并转入明日规划；没有阻碍时写“今日记录中未发现明确阻碍”。\n\n"
            "必须逐字使用以下 Markdown 结构，不得增加前言、后记或其他章节：\n"
            "📅 **[YYYY年MM月DD日] 工作日报**\n\n"
            "### 📝 本日工作概述\n"
            "> [用 1-2 句话概括核心工作和状态变化]\n\n"
            "### 🚀 今日主要成果与技术进展\n"
            "- **[模块名称]**\n"
            "  - **进展**：[实际完成内容]\n"
            "  - **技术要点/避坑**：[仅写记录中存在的技术事实]\n\n"
            "### ⚠️ 遇到问题与阻碍 (Blockers)\n"
            "- **[问题名称]**：[具体阻碍与现象]\n\n"
            "### 📅 明日规划\n"
            "- [针对阻碍的下一步行动]\n"
            "- [记录中已有的其他计划]\n\n"
            "查询日期必须等于日报日期，不加状态过滤，includeLinkedPlans=true。"
            "禁止创建、更新、完成或删除事件，也不要调用日报保存接口；Adapter 负责保存。\n"
        )
    media_edit_instructions = ""
    if event.get("event_type") == "idea_media_edit":
        media_edit_instructions = (
            "这是已有 Idea 的图片附件预处理任务，不是新建 Idea，也不是日程任务。\n"
            f"Media Job ID：{event.get('jobId')}\n"
            f"目标 Idea ID：{event.get('targetIdeaId')}\n"
            "只允许按以下顺序操作：\n"
            "1. 对唯一图片调用一次 mediaImageOcr，同时传 uploadId 和 jobId。\n"
            "2. OCR 成功后，根据 OCR 与用户上下文生成不超过 100 个字符的中文摘要，"
            "调用一次 ideaMediaJobComplete，传 jobId、summary、ocrEvidence。\n"
            "3. OCR 返回失败时调用一次 ideaMediaJobFail，然后停止。严禁重试 OCR。\n"
            "禁止调用 ideaCapture、evtQuery 或任何事件写接口。\n"
        )
    attachment_instructions = ""
    if event.get("event_type") != "idea_media_edit":
        attachment_instructions = (
            "When an event includes attachments, follow the Media Ideas rules in the SmartCore skill exactly. "
            "This is a mandatory attachment task: do not reply NO_REPLY, do not expose IDs, and do not claim an "
            "attachment is missing when the compact event JSON lists it. Call mediaImageOcr exactly once for every image, "
            "even without user text, and pass every returned ocrEvidence to ideaCapture. Documents must be stored without "
            "reading or OCR. If the text explicitly asks to "
            "create a schedule, reminder, or DDL, follow that explicit instruction instead.\n"
        )
    return (
        "You are SmartCore Agent handling one forwarded SmartCore event.\n"
        "Do not run onboarding, identity setup, or general assistant bootstrap flows.\n"
        "Use SmartCore Agent APIs for all data operations.\n"
        "Do not access SQLite files, Docker volumes, backups, or SmartCore internals directly.\n"
        f"SmartCore base URL: {base_url}\n"
        f"Read the SmartCore API token from {token_file} only inside the command that calls SmartCore. Never print it.\n"
        "Required SmartCore header name: X-SmartCore-Agent-Token.\n"
        f"{auth_instructions}"
        "For one local day, query with date: YYYY-MM-DD. For a wider range, use only "
        "timeRange.start and timeRange.end with absolute ISO-8601 values.\n"
        "Never send start_time, end_time, filter, or locally filter a truncated response. "
        "Check ok/errors and read results from data.items before answering.\n"
        "For event queries, use the bundled skills/smartcore/scripts/query_events.py helper "
        "instead of constructing curl commands.\n"
        "Do not call Feishu feedback endpoints or sendFeishu tools; the Adapter owns final delivery.\n"
        "Return exactly one concise user-facing final answer in finalAssistantVisibleText.\n"
        f"{attachment_instructions}"
        "On failure or ambiguity, return one concise clarification or error message.\n"
        f"{media_edit_instructions}"
        f"{daily_summary_instructions}"
        f"Bound reply chat_id: {reply_chat_id or 'missing'}\n"
        f"User routing context: {json.dumps(user, ensure_ascii=False) if user else '{}'}\n"
        "If the target is ambiguous, return a concise clarification instead of guessing.\n"
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


def extract_final_text(stdout: str) -> str:
    try:
        payload = json.loads(stdout)
    except Exception:
        return ""
    value = find_key(payload, "finalAssistantVisibleText")
    return value.strip() if isinstance(value, str) else ""


def daily_report_title(report_date: str) -> str:
    try:
        year, month, day = (int(part) for part in report_date.split("-"))
    except (TypeError, ValueError):
        return ""
    return f"📅 **{year:04d}年{month:02d}月{day:02d}日 工作日报**"


def normalize_daily_report(text: str, report_date: str) -> tuple[str, str | None]:
    """Extract and validate the only report shape allowed to reach persistence."""
    title = daily_report_title(report_date)
    if not title:
        return "", "invalid report date"
    start = text.find(title)
    if start < 0:
        return "", "missing exact report title"
    report = text[start:].strip()
    if report.count(title) != 1:
        return "", "report title must appear exactly once"
    positions: list[int] = []
    for heading in DAILY_HEADINGS:
        if report.count(heading) != 1:
            return "", f"heading count invalid: {heading}"
        positions.append(report.index(heading))
    if positions != sorted(positions) or positions[0] <= 0:
        return "", "daily report headings are out of order"
    leaked_markers = (
        "now let me",
        "analysis of ",
        "skip (auxiliary",
        "keep (substantive",
        "tool output",
        "finalassistantvisibletext",
    )
    lowered = report.lower()
    if any(marker in lowered for marker in leaked_markers):
        return "", "analysis or tool narration leaked into report"
    overview_start = positions[0] + len(DAILY_HEADINGS[0])
    overview = report[overview_start:positions[1]]
    if not re.search(r"[\u4e00-\u9fff]", overview):
        return "", "overview is not Chinese"
    return report, None


def build_daily_retry_prompt(event: dict[str, Any], *, scope_file: str) -> str:
    return (
        build_prompt(event, scope_file=scope_file)
        + "\n\n上一次输出因格式或语言不合格已被 Adapter 拒绝。"
        "请重新查询并直接输出最终中文日报。第一个字符必须是 📅，"
        "四个规定章节各出现一次；不要输出任何分析、筛选过程、英文前言或后记。"
    )


def normalize_media_reply(text: str) -> str:
    """Drop model/tool narration before the required card-title heading."""
    match = re.search(r"(?m)^#{1,2} +\S.*$", text)
    return text[match.start():].strip() if match else text.strip()


def split_reply_card(text: str) -> tuple[str, str]:
    """Keep a leading Markdown heading in the card header only."""
    lines = text.strip().splitlines()
    if not lines:
        return "SmartCore", ""
    first = lines[0].strip()
    if first.startswith("# ") or first.startswith("## "):
        title = first.lstrip("#").strip()[:60] or "SmartCore"
        return title, "\n".join(lines[1:]).lstrip() or "已处理。"
    if first.startswith("📅 **") and first.endswith("**"):
        title = first.replace("**", "")[:60]
        return title, "\n".join(lines[1:]).lstrip() or "已生成日报。"
    return first[:60] or "SmartCore", text.strip()


def send_final_reply(event: dict[str, Any], text: str) -> None:
    scope = str(event.get("agentScope") or "").strip()
    if not scope:
        raise ValueError("missing agent scope")

    token_file = Path(
        os.environ.get(
            "SMARTCORE_AGENT_TOKEN_FILE",
            "/root/.openclaw/smartcore-agent-api-token",
        )
    )
    token = token_file.read_text(encoding="utf-8").strip()
    if not token:
        raise ValueError("empty SmartCore agent token")

    base_url = os.environ.get("SMARTCORE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    title, content = split_reply_card(text)
    request = urllib.request.Request(
        f"{base_url}/agent/feedback/send_text",
        data=json.dumps({"text": content, "title": title}, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-SmartCore-Agent-Token": token,
            "X-SmartCore-Agent-Scope": scope,
        },
        method="POST",
    )
    with urllib.request.urlopen(
        request,
        timeout=int(os.environ.get("SMARTCORE_REPLY_TIMEOUT_SECONDS", "15")),
    ) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        errors = payload.get("errors") if isinstance(payload, dict) else None
        raise RuntimeError(f"SmartCore reply rejected: {compact(errors, 300)}")


def save_daily_summary(
    event: dict[str, Any],
    *,
    stat: str,
    content: str | None = None,
    error_message: str | None = None,
) -> None:
    scope = str(event.get("agentScope") or "").strip()
    report_date = str(event.get("reportDate") or "").strip()
    if not scope or not report_date:
        raise ValueError("daily summary event is missing scope or report date")
    token_file = Path(
        os.environ.get(
            "SMARTCORE_AGENT_TOKEN_FILE",
            "/root/.openclaw/smartcore-agent-api-token",
        )
    )
    token = token_file.read_text(encoding="utf-8").strip()
    if not token:
        raise ValueError("empty SmartCore agent token")
    base_url = os.environ.get("SMARTCORE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    request = urllib.request.Request(
        f"{base_url}/agent/daily-summary",
        data=json.dumps(
            {
                "reportDate": report_date,
                "content": content,
                "stat": stat,
                "errorMessage": error_message,
            },
            ensure_ascii=False,
        ).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-SmartCore-Agent-Token": token,
            "X-SmartCore-Agent-Scope": scope,
        },
        method="POST",
    )
    with urllib.request.urlopen(
        request,
        timeout=int(os.environ.get("SMARTCORE_REPLY_TIMEOUT_SECONDS", "15")),
    ) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        errors = payload.get("errors") if isinstance(payload, dict) else None
        raise RuntimeError(f"SmartCore daily summary rejected: {compact(errors, 300)}")


def mark_daily_summary_failed(event: dict[str, Any], error_message: str) -> None:
    if event.get("event_type") != "daily_summary":
        return
    try:
        save_daily_summary(
            event,
            stat="failed",
            error_message=compact(error_message, 500),
        )
    except Exception as exc:
        log(
            "daily summary failure state not saved",
            event_id=event.get("event_id"),
            error=repr(exc),
        )


def deliver_reply(event: dict[str, Any], text: str) -> bool:
    try:
        send_final_reply(event, text)
        log("final reply delivered", event_id=event.get("event_id"))
        return True
    except Exception as exc:
        log("final reply failed", event_id=event.get("event_id"), error=repr(exc))
        return False


def create_task_scope_file(workspace: Path, event: dict[str, Any], scope: str) -> Path:
    """Create a short-lived, task-isolated scope file for the OpenClaw gateway."""
    scope_dir = workspace / ".smartcore-task-scopes"
    scope_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    task_id = safe_session_part(
        str(event.get("message_id") or event.get("event_id") or "task")
    )
    path = scope_dir / f"{task_id}-{secrets.token_urlsafe(12)}"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(scope)
    return path


def run_openclaw(event: dict[str, Any]) -> None:
    started = time.monotonic()
    chat = event.get("chat") if isinstance(event.get("chat"), dict) else {}
    user = event.get("user") if isinstance(event.get("user"), dict) else {}
    target = event.get("chat_id") or chat.get("chat_id") or user.get("user_id") or event.get("event_id") or "unknown"
    agent_id = os.environ.get("OPENCLAW_AGENT_ID", "smartcore")
    session_prefix = os.environ.get("OPENCLAW_SESSION_PREFIX", f"agent:{agent_id}:smartcore-feishu")
    # Media and scheduled reports are independent tasks. Reusing a conversational
    # session can leak old facts into either workflow.
    if isinstance(event.get("attachments"), list):
        target = f"{target}-{event.get('message_id') or event.get('event_id') or time.time_ns()}"
    elif event.get("event_type") == "daily_summary":
        target = f"{target}-daily-{event.get('reportDate') or event.get('event_id')}"
    session_key = f"{session_prefix}-{safe_session_part(str(target))}"
    workspace = os.environ.get("OPENCLAW_WORKSPACE", "/root/.openclaw-smartcore-workspace")
    env = os.environ.copy()
    path_entries = [openclaw_node_bin(), "/root/.openclaw/bin", env.get("PATH", "")]
    env["PATH"] = ":".join(entry for entry in path_entries if entry)
    # Gateway tool processes do not reliably inherit adapter environment
    # variables.  Deliberately remove any ambient scope and use a task-local
    # file that the gateway's workspace can read.
    env.pop("SMARTCORE_AGENT_SCOPE", None)
    scope = str(event.get("agentScope") or "").strip()
    if not scope:
        reply_delivered = deliver_reply(event, FAILURE_REPLY)
        log(
            "openclaw rejected event without scope",
            event_id=event.get("event_id"),
            reply_delivered=reply_delivered,
        )
        return
    scope_file = create_task_scope_file(Path(workspace), event, scope)
    relative_scope_file = scope_file.relative_to(workspace).as_posix()
    cmd = [
        os.environ.get("OPENCLAW_BIN", "/root/.openclaw/bin/openclaw"),
        "agent",
        "--agent", agent_id,
        "--session-key", session_key,
        "--thinking", os.environ.get("OPENCLAW_THINKING", "low"),
        "--message", build_prompt(event, scope_file=relative_scope_file),
        "--json",
    ]
    if isinstance(event.get("attachments"), list):
        cmd[cmd.index("--thinking"):cmd.index("--thinking")] = ["--model", os.environ.get("OPENCLAW_MEDIA_MODEL", "deepseek-v4-pro")]
    try:
        result = subprocess.run(
            cmd,
            env=env,
            cwd=workspace,
            text=True,
            capture_output=True,
            timeout=int(os.environ.get("OPENCLAW_TIMEOUT_SECONDS", "600")),
        )
        final_text = extract_final_text(result.stdout)
        succeeded = result.returncode == 0 and bool(final_text)
        daily_validation_error: str | None = None
        if succeeded and isinstance(event.get("attachments"), list):
            final_text = normalize_media_reply(final_text)
        if succeeded and event.get("event_type") == "daily_summary":
            final_text, daily_validation_error = normalize_daily_report(
                final_text,
                str(event.get("reportDate") or ""),
            )
            if daily_validation_error:
                log(
                    "daily summary rejected before persistence",
                    event_id=event.get("event_id"),
                    reason=daily_validation_error,
                )
                retry_cmd = list(cmd)
                retry_cmd[retry_cmd.index("--session-key") + 1] = f"{session_key}-format-retry"
                retry_cmd[retry_cmd.index("--message") + 1] = build_daily_retry_prompt(
                    event,
                    scope_file=relative_scope_file,
                )
                result = subprocess.run(
                    retry_cmd,
                    env=env,
                    cwd=workspace,
                    text=True,
                    capture_output=True,
                    timeout=int(os.environ.get("OPENCLAW_TIMEOUT_SECONDS", "600")),
                )
                retry_text = extract_final_text(result.stdout)
                final_text, daily_validation_error = normalize_daily_report(
                    retry_text,
                    str(event.get("reportDate") or ""),
                )
            succeeded = result.returncode == 0 and bool(final_text) and not daily_validation_error
        duration_ms = int((time.monotonic() - started) * 1000)
        if succeeded and event.get("event_type") == "daily_summary":
            try:
                save_daily_summary(event, stat="complete", content=final_text)
            except Exception as exc:
                succeeded = False
                mark_daily_summary_failed(event, f"persistence failed: {type(exc).__name__}")
                log(
                    "daily summary persistence failed",
                    event_id=event.get("event_id"),
                    error=repr(exc),
                )
        elif not succeeded:
            mark_daily_summary_failed(
                event,
                daily_validation_error
                or f"OpenClaw returned code {result.returncode} without a valid final report",
            )
        reply_text = final_text if succeeded else FAILURE_REPLY
        reply_delivered = False
        if event.get("source") != "web":
            reply_delivered = deliver_reply(event, reply_text)
        log(
            "openclaw finished",
            event_id=event.get("event_id"),
            returncode=result.returncode,
            duration_ms=duration_ms,
            reply_delivered=reply_delivered,
            **summarize_openclaw(result.stdout, result.stderr),
        )
    except Exception as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        mark_daily_summary_failed(event, f"OpenClaw execution failed: {type(exc).__name__}")
        reply_delivered = deliver_reply(event, FAILURE_REPLY)
        log(
            "openclaw failed",
            event_id=event.get("event_id"),
            duration_ms=duration_ms,
            reply_delivered=reply_delivered,
            error=repr(exc),
        )
    finally:
        scope_file.unlink(missing_ok=True)


class Handler(BaseHTTPRequestHandler):
    server_version = "SmartCoreOpenClawAdapter/0.5"

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
    skill_changed = sync_bundled_skill()
    runtime_config_changed = write_skill_runtime_config()
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "18790"))
    server = ThreadingHTTPServer((host, port), Handler)
    log(
        "adapter started",
        host=host,
        port=port,
        agent=os.environ.get("OPENCLAW_AGENT_ID", "smartcore"),
        thinking=os.environ.get("OPENCLAW_THINKING", "low"),
        skill_updated=skill_changed,
        skill_ready=bundled_skill_ready(),
        skill_runtime_updated=runtime_config_changed,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
