from __future__ import annotations

from app.agent.feedback_routes import createFeedbackRouter, ensure_feedback_tools
from app.agent.routes import _AGENT_TOOLS
from app.feishu.cards import (
    build_message_card,
    build_operation_success_card,
    build_query_result_card,
    build_reminder_card,
    normalize_card,
)
from app.new_core.notify import buildReminderCard


def test_card_20_is_normalized_for_interactive_message_api() -> None:
    normalized = normalize_card(
        {
            "schema": "2.0",
            "header": {"title": {"tag": "plain_text", "content": "Title"}},
            "body": {
                "elements": [
                    {"tag": "div", "text": {"tag": "plain_text", "content": "Body"}}
                ]
            },
        }
    )

    assert "schema" not in normalized
    assert "body" not in normalized
    assert normalized["header"]["template"] == "blue"
    assert normalized["elements"][0]["tag"] == "div"


def test_structured_cards_use_top_level_elements() -> None:
    query_card = build_query_result_card(
        title="Today",
        items=[{"title": "Review", "evtType": "plan", "stTime": "20:00"}],
    )
    success_card = build_operation_success_card(
        content="Created",
        event={"title": "Review", "evtType": "plan"},
    )
    reminder_card = build_reminder_card(
        evt_id="evt-1",
        title="Review",
        content="Time is up",
    )

    for card in (query_card, success_card, reminder_card):
        assert "elements" in card
        assert "body" not in card
        assert "schema" not in card

    action = reminder_card["elements"][-1]
    assert action["tag"] == "action"
    assert action["actions"][0]["value"]["evtId"] == "evt-1"


def test_scheduler_reminder_card_uses_compatible_shape() -> None:
    card = buildReminderCard(evtId="evt-2", title="Task", content="Done?")
    assert card["header"]["template"] == "orange"
    assert isinstance(card["elements"], list)
    assert "body" not in card


def test_message_card_converts_markdown_table_to_feishu_columns() -> None:
    card = build_message_card(
        content=(
            "这是明天的安排：\n\n"
            "| 时间 | 事项 |\n"
            "| --- | --- |\n"
            "| 09:30–10:00 | 起床吃早饭 |\n"
            "| 10:00–12:00 | 准备汇报材料 |\n\n"
            "下午继续准备。"
        )
    )

    assert card["elements"][0]["text"]["content"] == "这是明天的安排："
    header = card["elements"][1]
    assert header["tag"] == "column_set"
    assert header["background_style"] == "grey"
    assert [
        column["elements"][0]["text"]["content"]
        for column in header["columns"]
    ] == ["**时间**", "**事项**"]
    first_row = card["elements"][2]
    assert [
        column["elements"][0]["text"]["content"]
        for column in first_row["columns"]
    ] == ["09:30–10:00", "起床吃早饭"]
    assert card["elements"][-1]["text"]["content"] == "下午继续准备。"


def test_message_card_keeps_pipes_outside_tables_as_markdown() -> None:
    content = "字段 A | 字段 B\n这不是表格"
    card = build_message_card(content=content)

    assert card["elements"] == [
        {"tag": "div", "text": {"tag": "lark_md", "content": content}}
    ]


def test_message_card_does_not_convert_table_inside_code_fence() -> None:
    content = "```\n| A | B |\n| --- | --- |\n| 1 | 2 |\n```"
    card = build_message_card(content=content)

    assert card["elements"] == [
        {"tag": "div", "text": {"tag": "lark_md", "content": content}}
    ]


def test_agent_tools_expose_structured_card_endpoints() -> None:
    ensure_feedback_tools()
    names = {tool["name"] for tool in _AGENT_TOOLS}
    assert "sendFeishuQueryResultCard" in names
    assert "sendFeishuOperationSuccessCard" in names
    assert "sendFeishuReminderCard" in names

    paths = {route.path for route in createFeedbackRouter().routes}
    assert "/agent/feedback/send_card" in paths
    assert "/agent/feedback/send_query_result_card" in paths
    assert "/agent/feedback/send_operation_success_card" in paths
    assert "/agent/feedback/send_reminder_card" in paths
