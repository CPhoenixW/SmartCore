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
        },
    }
    assert requests[0]["model"] == "deepseek-chat"
    assert "今晚八点提醒我做程设作业" in json.dumps(requests[0], ensure_ascii=False)


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
