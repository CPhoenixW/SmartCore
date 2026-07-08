from __future__ import annotations

from app.agent.feedback_routes import createFeedbackRouter, ensure_feedback_tools
from app.agent.routes import _AGENT_TOOLS
from app.feishu.cards import (
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
