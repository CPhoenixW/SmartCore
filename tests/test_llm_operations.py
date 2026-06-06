from __future__ import annotations

import json
from datetime import datetime

import httpx

from app.llm.deepseek import DeepSeekOperationParser
from app.operations.parser import (
    CompositeOperationParser,
    ParsedOperation,
    RuleBasedOperationParser,
)
from app.secretary.rules import DEFAULT_TZ


def test_deepseek_parser_converts_free_form_reminder_to_life_event() -> None:
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content.decode()))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "operation": "create",
                                    "resource": "event",
                                    "fields": {
                                        "event_type": "life_event",
                                        "title": "做程设作业",
                                        "scheduled_at": "2026-06-05T20:00:00+08:00",
                                        "reminder_lead_minutes": 15,
                                    },
                                    "confidence": 0.88,
                                    "needs_confirmation": True,
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            },
        )

    parser = DeepSeekOperationParser(
        api_key="test-key",
        base_url="https://api.deepseek.test",
        model="deepseek-chat",
        tz=DEFAULT_TZ,
        transport=httpx.MockTransport(handler),
    )

    operation = parser.parse(
        "今晚八点提醒我做程设作业",
        source="feishu",
        now=datetime(2026, 6, 5, 9, 0, tzinfo=DEFAULT_TZ),
    )

    assert operation.action_name == "create_event"
    assert operation.needs_confirmation is True
    assert operation.confidence == 0.88
    assert operation.payload == {
        "operation": "create",
        "resource": "event",
        "selector": {},
        "fields": {
            "event_type": "life_event",
            "title": "做程设作业",
            "scheduled_at": "2026-06-05T20:00:00+08:00",
            "reminder_lead_minutes": 15,
        },
    }
    assert requests[0]["model"] == "deepseek-chat"
    assert "今晚八点提醒我做程设作业" in json.dumps(requests[0], ensure_ascii=False)
    assert "reminder_lead_minutes" in json.dumps(requests[0], ensure_ascii=False)


def test_deepseek_parser_accepts_unified_update_life_event_operation() -> None:
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content.decode()))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "operation": "update",
                                    "resource": "event",
                                    "selector": {"event_type": "life_event", "id": 12},
                                    "fields": {
                                        "scheduled_at": "2026-06-05T20:30:00+08:00"
                                    },
                                    "confidence": 0.82,
                                    "needs_confirmation": True,
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            },
        )

    parser = DeepSeekOperationParser(
        api_key="test-key",
        base_url="https://api.deepseek.test",
        model="deepseek-chat",
        tz=DEFAULT_TZ,
        transport=httpx.MockTransport(handler),
    )

    operation = parser.parse(
        "把 12 号事项改到 20:30",
        source="feishu",
        now=datetime(2026, 6, 5, 9, 0, tzinfo=DEFAULT_TZ),
    )

    assert operation.action_name == "update_event"
    assert operation.payload == {
        "operation": "update",
        "resource": "event",
        "selector": {"event_type": "life_event", "id": 12},
        "fields": {"scheduled_at": "2026-06-05T20:30:00+08:00"},
    }
    assert operation.needs_confirmation is True
    prompt = json.dumps(requests[0], ensure_ascii=False)
    assert "operation" in prompt
    assert "selector" in prompt
    assert "create/update/delete/query" in prompt


def test_deepseek_parser_accepts_unified_event_interface() -> None:
    requests: list[dict] = []
    responses = iter(
        [
            {
                "operation": "create",
                "resource": "event",
                "fields": {
                    "event_type": "assignment",
                    "title": "线代作业",
                    "due_at": "2026-06-10T20:00:00+08:00",
                },
                "confidence": 0.91,
                "needs_confirmation": True,
            },
            {
                "operation": "update",
                "resource": "event",
                "selector": {"event_type": "life_event", "id": 7},
                "fields": {
                    "title": "改成跑步",
                    "scheduled_at": "2026-06-05T21:00:00+08:00",
                },
                "confidence": 0.9,
                "needs_confirmation": True,
            },
            {
                "operation": "delete",
                "resource": "event",
                "selector": {"event_type": "assignment", "id": 8},
                "fields": {},
                "confidence": 0.88,
                "needs_confirmation": True,
            },
            {
                "operation": "read",
                "resource": "event",
                "fields": {"event_type": "life_event", "status": "open"},
                "confidence": 0.93,
                "needs_confirmation": False,
            },
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content.decode()))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(next(responses), ensure_ascii=False)
                        }
                    }
                ]
            },
        )

    parser = DeepSeekOperationParser(
        api_key="test-key",
        base_url="https://api.deepseek.test",
        model="deepseek-chat",
        tz=DEFAULT_TZ,
        transport=httpx.MockTransport(handler),
    )

    create = parser.parse(
        "新增线代作业，下周三晚上八点截止",
        source="feishu",
        now=datetime(2026, 6, 5, 9, 0, tzinfo=DEFAULT_TZ),
    )
    update = parser.parse(
        "把 7 号事项改成晚上九点跑步",
        source="feishu",
        now=datetime(2026, 6, 5, 9, 0, tzinfo=DEFAULT_TZ),
    )
    delete = parser.parse(
        "删除 8 号作业",
        source="feishu",
        now=datetime(2026, 6, 5, 9, 0, tzinfo=DEFAULT_TZ),
    )
    query = parser.parse(
        "查询未完成生活事项",
        source="feishu",
        now=datetime(2026, 6, 5, 9, 0, tzinfo=DEFAULT_TZ),
    )

    assert create.action_name == "create_event"
    assert create.payload["operation"] == "create"
    assert create.payload["resource"] == "event"
    assert create.payload["fields"]["event_type"] == "assignment"
    assert update.action_name == "update_event"
    assert update.payload["selector"] == {"event_type": "life_event", "id": 7}
    assert delete.action_name == "delete_event"
    assert delete.payload["operation"] == "delete"
    assert query.action_name == "query_event"
    assert query.needs_confirmation is False
    assert query.payload["operation"] == "query"
    prompt = json.dumps(requests[0], ensure_ascii=False)
    assert "resource=event" in prompt or '"event"' in prompt
    assert "course_session" in prompt
    assert "assignment" in prompt
    assert "life_event" in prompt


def test_deepseek_parser_rejects_reminder_resource() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "operation": "create",
                                    "resource": "reminder",
                                    "fields": {
                                        "title": "吃饭",
                                        "scheduled_at": "2026-06-05T22:00:00+08:00",
                                    },
                                    "confidence": 0.95,
                                    "needs_confirmation": True,
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            },
        )

    parser = DeepSeekOperationParser(
        api_key="test-key",
        base_url="https://api.deepseek.test",
        model="deepseek-chat",
        tz=DEFAULT_TZ,
        transport=httpx.MockTransport(handler),
    )

    import pytest

    with pytest.raises(ValueError, match="unsupported resource"):
        parser.parse(
            "今晚十点提醒我吃饭",
            source="feishu",
            now=datetime(2026, 6, 5, 13, 40, tzinfo=DEFAULT_TZ),
        )


def test_deepseek_parser_accepts_unified_delete_life_event_operation() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "operation": "delete",
                                    "resource": "event",
                                    "selector": {"event_type": "life_event", "id": 12},
                                    "fields": {},
                                    "confidence": 0.86,
                                    "needs_confirmation": True,
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            },
        )

    parser = DeepSeekOperationParser(
        api_key="test-key",
        base_url="https://api.deepseek.test",
        model="deepseek-chat",
        tz=DEFAULT_TZ,
        transport=httpx.MockTransport(handler),
    )

    operation = parser.parse(
        "删除 12 号事项",
        source="feishu",
        now=datetime(2026, 6, 5, 9, 0, tzinfo=DEFAULT_TZ),
    )

    assert operation.action_name == "delete_event"
    assert operation.payload["operation"] == "delete"
    assert operation.payload["resource"] == "event"
    assert operation.payload["selector"] == {"event_type": "life_event", "id": 12}


def test_composite_parser_falls_back_to_llm_when_rules_do_not_match() -> None:
    class FakeLLMParser:
        def parse(self, text: str, *, source: str, now=None):
            assert text == "今晚八点提醒我做程设作业"
            return RuleBasedOperationParser(tz=DEFAULT_TZ).parse(
                "添加事项 做程设作业",
                source=source,
            )

    parser = CompositeOperationParser(
        rule_parser=RuleBasedOperationParser(tz=DEFAULT_TZ),
        llm_parser=FakeLLMParser(),
    )

    operation = parser.parse("今晚八点提醒我做程设作业", source="feishu")

    assert operation.action_name == "create_event"
    assert operation.payload["fields"]["title"] == "做程设作业"


def test_composite_parser_delegates_candidate_selection_to_llm() -> None:
    class FakeLLMParser:
        def select_candidates(self, *, raw_text, parsed, candidates):
            assert raw_text == "把程设作业改到十点"
            assert parsed.action_name == "update_event"
            assert candidates == [
                {
                    "event_type": "life_event",
                    "id": 7,
                    "status": "pending",
                    "time_label": "2026-06-06 20:00",
                    "title": "做程序设计作业",
                }
            ]
            return {
                "match_status": "single",
                "selected_ids": [{"event_type": "life_event", "id": 7}],
                "confidence": 0.93,
                "reason": "语义匹配",
            }

    parser = CompositeOperationParser(
        rule_parser=RuleBasedOperationParser(tz=DEFAULT_TZ),
        llm_parser=FakeLLMParser(),
    )
    parsed = ParsedOperation(
        source="feishu",
        raw_text="把程设作业改到十点",
        action_name="update_event",
        payload={"operation": "update", "resource": "event", "selector": {}, "fields": {}},
        confidence=0.9,
        needs_confirmation=True,
    )

    selection = parser.select_candidates(
        raw_text="把程设作业改到十点",
        parsed=parsed,
        candidates=[
            {
                "event_type": "life_event",
                "id": 7,
                "status": "pending",
                "time_label": "2026-06-06 20:00",
                "title": "做程序设计作业",
            }
        ],
    )

    assert selection["match_status"] == "single"
    assert selection["selected_ids"] == [{"event_type": "life_event", "id": 7}]
