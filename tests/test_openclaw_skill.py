from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "openclaw" / "skills" / "smartcore" / "SKILL.md"
TOOLS_REF = ROOT / "openclaw" / "skills" / "smartcore" / "references" / "smartcore-tools.md"
RUNTIME_DOC = ROOT / "doc" / "10-openclaw-skill-runtime.md"


def test_openclaw_smartcore_skill_exists_and_sets_boundaries() -> None:
    content = SKILL.read_text(encoding="utf-8")
    required = (
        "SmartCore",
        "OpenClaw",
        "DeepSeek",
        "/agent/tools",
        "/agent/db/query_events",
        "/agent/db/create_event",
        "/agent/db/update_event",
        "/agent/db/delete_event",
        "/agent/feedback/",
        "must never access SQLite",
        "must not construct Feishu card JSON",
        "time_range.start",
        "time_range.end",
    )
    for phrase in required:
        assert phrase in content


def test_openclaw_smartcore_tool_reference_documents_runtime_rules() -> None:
    content = TOOLS_REF.read_text(encoding="utf-8")
    for phrase in (
        "query_events",
        "create_event",
        "update_event",
        "delete_event",
        "send_text",
        "send_query_result_card",
        "send_operation_success_card",
        "send_reminder_card",
        "pending_confirmation",
        "Clarify before destructive actions",
    ):
        assert phrase in content


def test_openclaw_runtime_plan_keeps_smartcore_authoritative() -> None:
    content = RUNTIME_DOC.read_text(encoding="utf-8")
    for phrase in (
        "SmartCore remains the reliable business system",
        "OpenClaw becomes the agent orchestration layer",
        "DeepSeek is the model provider",
        "Codex are development tools only",
        "scheduler reminder loop",
        "dashboard exposes an agent status page",
    ):
        assert phrase in content
