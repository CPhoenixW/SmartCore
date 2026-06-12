from pathlib import Path

DOC = (
    Path(__file__).resolve().parents[1]
    / "doc"
    / "07-agent-operation-notification-architecture.md"
)
OPENCLAW_DOC = (
    Path(__file__).resolve().parents[1]
    / "doc"
    / "09-openclaw-smartcore-bridge.md"
)


def test_agent_architecture_doc_exists_and_names_core_layers() -> None:
    content = DOC.read_text(encoding="utf-8")
    for phrase in (
        "Semantic Layer",
        "Pending Operation",
        "Action Layer",
        "Resource Layer",
        "Event & Schedule Layer",
        "Notification Layer",
        "Channel Layer",
    ):
        assert phrase in content


def test_agent_architecture_doc_keeps_llm_out_of_direct_execution() -> None:
    content = DOC.read_text(encoding="utf-8")
    assert "LLM 只负责把自然语言翻译为结构化操作草案" in content
    assert "真正修改数据" in content
    assert "Action" in content


def test_openclaw_bridge_doc_defines_gateway_and_tool_boundaries() -> None:
    content = OPENCLAW_DOC.read_text(encoding="utf-8")
    for phrase in (
        "SmartCore Feishu Gateway",
        "OpenClaw owns natural-language",
        "GET /agent/tools",
        "POST /agent/db/query_events",
        "POST /agent/feedback/send_query_result_card",
        "Reminder Loop",
        "must never access the SQLite database file",
    ):
        assert phrase in content
