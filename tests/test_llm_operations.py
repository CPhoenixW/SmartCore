from __future__ import annotations

import json
from datetime import datetime

import httpx

from app.llm.deepseek import DeepSeekOperationParser
from app.operations.parser import CompositeOperationParser, RuleBasedOperationParser
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
                                    "action_name": "create_life_event",
                                    "resource": "life_event",
                                    "fields": {
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

    assert operation.action_name == "create_life_event"
    assert operation.needs_confirmation is True
    assert operation.confidence == 0.88
    assert operation.payload == {
        "resource": "life_event",
        "fields": {
            "title": "做程设作业",
            "scheduled_at": "2026-06-05T20:00:00+08:00",
            "reminder_lead_minutes": 15,
        },
    }
    assert requests[0]["model"] == "deepseek-chat"
    assert "今晚八点提醒我做程设作业" in json.dumps(requests[0], ensure_ascii=False)
    assert "reminder_lead_minutes" in json.dumps(requests[0], ensure_ascii=False)


def test_deepseek_parser_accepts_unified_update_reminder_operation() -> None:
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
                                    "resource": "reminder",
                                    "selector": {"id": 12},
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
        "把 12 号提醒改到 20:30",
        source="feishu",
        now=datetime(2026, 6, 5, 9, 0, tzinfo=DEFAULT_TZ),
    )

    assert operation.action_name == "update_reminder"
    assert operation.payload == {
        "operation": "update",
        "resource": "reminder",
        "selector": {"id": 12},
        "fields": {"scheduled_at": "2026-06-05T20:30:00+08:00"},
    }
    assert operation.needs_confirmation is True
    prompt = json.dumps(requests[0], ensure_ascii=False)
    assert "operation" in prompt
    assert "selector" in prompt
    assert "create/read/update/cancel" in prompt


def test_deepseek_parser_normalizes_create_reminder_to_life_event() -> None:
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

    operation = parser.parse(
        "今晚十点提醒我吃饭",
        source="feishu",
        now=datetime(2026, 6, 5, 13, 40, tzinfo=DEFAULT_TZ),
    )

    assert operation.action_name == "create_life_event"
    assert operation.payload == {
        "operation": "create",
        "resource": "life_event",
        "selector": {},
        "fields": {
            "title": "吃饭",
            "scheduled_at": "2026-06-05T22:00:00+08:00",
            "reminder_lead_minutes": 15,
        },
    }


def test_deepseek_parser_accepts_unified_cancel_reminder_operation() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "operation": "cancel",
                                    "resource": "reminder",
                                    "selector": {"id": 12},
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
        "取消 12 号提醒",
        source="feishu",
        now=datetime(2026, 6, 5, 9, 0, tzinfo=DEFAULT_TZ),
    )

    assert operation.action_name == "cancel_reminder"
    assert operation.payload["operation"] == "cancel"
    assert operation.payload["resource"] == "reminder"
    assert operation.payload["selector"] == {"id": 12}


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

    assert operation.action_name == "create_life_event"
    assert operation.payload["fields"]["title"] == "做程设作业"
