from __future__ import annotations

import json
from datetime import datetime

import httpx
import pytest

from app.llm import deepseek
from app.llm.deepseek import DeepSeekOperationParser
from app.operations.parser import OperationParser, ParsedOperation
from app.secretary.rules import DEFAULT_TZ


def test_deepseek_parser_converts_free_form_reminder_to_schedule() -> None:
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
                                    "action": "create_event",
                                    "payload": {
                                        "event": {
                                            "event_type": "schedule",
                                            "title": "做程设作业",
                                            "start_at": "2026-06-05T20:00:00+08:00",
                                        }
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
        "action": "create_event",
        "payload": {
            "event": {
                "event_type": "schedule",
                "title": "做程设作业",
                "start_at": "2026-06-05T20:00:00+08:00",
            }
        },
        "source": "feishu",
        "raw_text": "今晚八点提醒我做程设作业",
        "confidence": 0.88,
        "needs_confirmation": True,
    }
    assert requests[0]["model"] == "deepseek-chat"
    assert "今晚八点提醒我做程设作业" in json.dumps(requests[0], ensure_ascii=False)
    assert "schedule" in json.dumps(requests[0], ensure_ascii=False)


def test_deepseek_parser_accepts_new_action_protocol() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "action": "create_event",
                                    "payload": {
                                        "event": {
                                            "event_type": "schedule",
                                            "title": "写作业",
                                            "start_at": "2026-06-07T22:00:00+08:00",
                                        }
                                    },
                                    "confidence": 0.9,
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
        "晚上十点提醒我写作业",
        source="feishu",
        now=datetime(2026, 6, 7, 18, 0, tzinfo=DEFAULT_TZ),
    )

    assert operation.action_name == "create_event"
    assert operation.payload["action"] == "create_event"
    assert operation.payload["payload"]["event"]["event_type"] == "schedule"
    assert operation.needs_confirmation is True


def test_deepseek_prompts_keep_candidate_selection_conservative() -> None:
    system_prompt = deepseek._SYSTEM_PROMPT
    selection_prompt = deepseek._SELECT_SYSTEM_PROMPT

    for event_type in ("course", "plan", "schedule", "deadline"):
        assert event_type in system_prompt
    for legacy_type in ("assignment", "life_event", "course_session"):
        assert legacy_type not in system_prompt
    assert "start_at" in system_prompt
    assert "end_at" in system_prompt
    assert "30" in system_prompt
    assert "15" in system_prompt
    assert "数据库 id" in system_prompt
    assert "今早" in system_prompt
    assert "06:00" in system_prompt
    assert "12:00" in system_prompt
    assert "needs_confirmation" in system_prompt
    assert "query_event 必须 false" in system_prompt
    assert "filter 必须包含 event_type、status、limit" in system_prompt
    assert "time_range 必须是半开区间" in system_prompt
    assert "标题/语义/时间" in selection_prompt
    assert "不要选择无关或弱相关候选" in selection_prompt
    assert "ref" in selection_prompt
    assert "selected_refs" in selection_prompt
    assert "ambiguous" in selection_prompt


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
                                    "action": "update_event",
                                    "payload": {
                                        "selector": {
                                            "mode": "semantic_ref",
                                            "filter": {"event_type": "all"},
                                            "target_description": "12 号事项",
                                        },
                                        "patch": {
                                            "start_at": "2026-06-05T20:30:00+08:00"
                                        },
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
    assert operation.payload["action"] == "update_event"
    assert operation.payload["payload"]["patch"]["start_at"] == "2026-06-05T20:30:00+08:00"
    assert operation.needs_confirmation is True
    prompt = json.dumps(requests[0], ensure_ascii=False)
    assert "update_event" in prompt
    assert "patch" in prompt


def test_deepseek_parser_accepts_unified_event_interface() -> None:
    requests: list[dict] = []
    responses = iter(
        [
            {
                "action": "create_event",
                "payload": {
                    "event": {
                        "event_type": "deadline",
                        "title": "线代作业",
                        "start_at": "2026-06-10T20:00:00+08:00",
                    }
                },
                "confidence": 0.91,
                "needs_confirmation": True,
            },
            {
                "action": "update_event",
                "payload": {
                    "selector": {"event_type": "schedule", "id": 7},
                    "patch": {
                        "title": "改成跑步",
                        "start_at": "2026-06-05T21:00:00+08:00",
                    },
                },
                "confidence": 0.9,
                "needs_confirmation": True,
            },
            {
                "action": "delete_event",
                "payload": {"selector": {"event_type": "deadline", "id": 8}},
                "confidence": 0.88,
                "needs_confirmation": True,
            },
            {
                "action": "query_event",
                "payload": {
                    "filter": {
                        "event_type": "all",
                        "status": ["pending", "active"],
                        "limit": 50,
                    }
                },
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
    assert create.payload["payload"]["event"]["event_type"] == "deadline"
    assert update.action_name == "update_event"
    assert update.payload["payload"]["patch"]["title"] == "改成跑步"
    assert delete.action_name == "delete_event"
    assert query.action_name == "query_event"
    assert query.needs_confirmation is False
    prompt = json.dumps(requests[0], ensure_ascii=False)
    assert "create_event" in prompt or "query_event" in prompt
    for event_type in ("course", "plan", "schedule", "deadline"):
        assert event_type in prompt


def test_deepseek_parser_rejects_missing_action() -> None:
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

    with pytest.raises(ValueError, match="action is required"):
        parser.parse(
            "今晚十点提醒我吃饭",
            source="feishu",
            now=datetime(2026, 6, 5, 13, 40, tzinfo=DEFAULT_TZ),
        )


def test_deepseek_parser_accepts_action_delete_schedule_operation() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "action": "delete_event",
                                    "payload": {
                                        "selector": {"event_type": "schedule", "id": 12}
                                    },
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
    assert operation.payload["action"] == "delete_event"
    assert operation.payload["payload"]["selector"] == {
        "event_type": "schedule",
        "id": 12,
    }


def test_operation_parser_delegates_parse_to_llm() -> None:
    class FakeLLMParser:
        def parse(self, text: str, *, source: str, now=None):
            assert text == "今晚八点提醒我做程设作业"
            return ParsedOperation(
                source=source,
                raw_text=text,
                action_name="create_event",
                payload={
                    "action": "create_event",
                    "source": source,
                    "raw_text": text,
                    "payload": {
                        "event": {
                            "event_type": "schedule",
                            "title": "做程设作业",
                            "start_at": "2026-06-05T20:00:00+08:00",
                        }
                    },
                },
                confidence=0.88,
                needs_confirmation=True,
            )

    parser = OperationParser(FakeLLMParser())

    operation = parser.parse("今晚八点提醒我做程设作业", source="feishu")

    assert operation.action_name == "create_event"
    assert operation.payload["payload"]["event"]["title"] == "做程设作业"


def test_operation_parser_delegates_candidate_selection_to_llm() -> None:
    class FakeLLMParser:
        def select_candidates(self, *, raw_text, parsed, candidates):
            assert raw_text == "把程设作业改到十点"
            assert parsed.action_name == "update_event"
            assert len(candidates) == 1
            assert candidates[0]["ref"] == "c1"
            return {
                "match_status": "single",
                "selected_refs": ["c1"],
                "confidence": 0.93,
                "reason": "语义匹配",
            }

        def parse(self, text: str, *, source: str, now=None):
            raise NotImplementedError

    parser = OperationParser(FakeLLMParser())
    parsed = ParsedOperation(
        source="feishu",
        raw_text="把程设作业改到十点",
        action_name="update_event",
        payload={
            "action": "update_event",
            "source": "feishu",
            "raw_text": "把程设作业改到十点",
            "payload": {
                "selector": {"mode": "semantic_ref", "target_description": "程设作业"},
                "patch": {"start_at": "2026-06-06T22:00:00+08:00"},
            },
        },
        confidence=0.9,
        needs_confirmation=True,
    )

    selection = parser.select_candidates(
        raw_text="把程设作业改到十点",
        parsed=parsed,
        candidates=[
            {
                "ref": "c1",
                "event_type": "schedule",
                "id": 7,
                "status": "pending",
                "time_label": "2026-06-06 20:00",
                "title": "做程序设计作业",
            }
        ],
    )

    assert selection["match_status"] == "single"
    assert selection["selected_refs"] == ["c1"]
