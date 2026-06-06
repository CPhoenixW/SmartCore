from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.operations.parser import ParsedOperation

_SUPPORTED_RESOURCES = frozenset({"event"})
_SUPPORTED_OPERATIONS = frozenset({"create", "read", "update", "delete", "query"})
_EVENT_TYPES = frozenset({"course_session", "assignment", "life_event"})
_EVENT_ACTIONS = {
    "create": "create_event",
    "update": "update_event",
    "delete": "delete_event",
    "query": "query_event",
}

_SYSTEM_PROMPT = """\
你是 SmartCore 个人调度助手的语义解析器。将用户的自然语言转为 JSON 操作草案。

只返回一个 JSON 对象，不要 markdown 代码块，不要额外说明。

优先使用统一 event 协议（resource=event）：
- operation: create/update/delete/query（兼容 read，归一化为 query）
- resource: 固定为 event
- fields.event_type: course_session、assignment 或 life_event 之一
- selector: 修改/删除/精确查询已有事件时含 id 和 event_type
- fields: 事件字段，如 title、course_name、due_at、scheduled_at、deadline_at、
  weekday、start_time、end_time、location、notes、reminder_lead_minutes
- confidence: 0 到 1 的浮点数
- needs_confirmation: 布尔值；query 应为 false，写操作应为 true

create + event + assignment: fields 含 event_type=assignment、title、due_at。
create + event + life_event: fields 含 event_type=life_event、title、scheduled_at 等。
create + event + course_session: fields 含 event_type=course_session、course_name、
weekday、start_time、end_time、location 等。
update/delete + event: selector 必须含 id 和 event_type。
query + event: fields 含 event_type（all/assignment/life_event/course_session）和 status。

当用户说“提醒我……”并给出时间时，必须输出 create + event + life_event，
不要输出 create + reminder；Reminder 是系统内部发送队列，不是用户直接创建的资源。
当用户想修改/删除提醒事项时，输出 update/delete + event + life_event，而不是 reminder。
"""


class DeepSeekOperationParser:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        tz: ZoneInfo,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._tz = tz
        self._transport = transport
        self._timeout = timeout

    def parse(
        self,
        text: str,
        *,
        source: str,
        now: datetime | None = None,
    ) -> ParsedOperation:
        if now is None:
            now = datetime.now(self._tz)
        raw_content = self._call_chat_completions(text, now)
        data = self._parse_json_content(raw_content)
        action_name, payload = self._normalize_operation(data)
        return ParsedOperation(
            source=source,
            raw_text=text,
            action_name=action_name,
            payload=payload,
            confidence=float(data.get("confidence", 0.5)),
            needs_confirmation=bool(data.get("needs_confirmation", True)),
        )

    def _call_chat_completions(self, text: str, now: datetime) -> str:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"当前时间：{now.isoformat()}\n"
                        f"用户输入：{text}\n"
                        "请输出 JSON 操作草案。"
                    ),
                },
            ],
            "response_format": {"type": "json_object"},
        }
        with httpx.Client(
            base_url=self._base_url,
            timeout=self._timeout,
            transport=self._transport,
        ) as client:
            response = client.post(
                "/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
            )
            if response.is_error:
                raise ValueError(
                    f"deepseek request failed: {response.status_code} {response.text}"
                )
            body = response.json()
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ValueError("deepseek response missing choices")
        message = choices[0].get("message", {})
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("deepseek response missing message content")
        return content

    def _parse_json_content(self, content: str) -> dict[str, Any]:
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"deepseek returned invalid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("deepseek JSON must be an object")
        return data

    def _normalize_operation(self, data: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        if "operation" not in data:
            raise ValueError("operation is required")
        return self._normalize_unified_operation(data)

    def _normalize_unified_operation(
        self, data: dict[str, Any]
    ) -> tuple[str, dict[str, Any]]:
        operation = data.get("operation")
        if operation == "read":
            operation = "query"
        if operation not in _SUPPORTED_OPERATIONS:
            raise ValueError(f"unsupported operation: {operation!r}")
        resource = data.get("resource")
        if resource not in _SUPPORTED_RESOURCES:
            raise ValueError(f"unsupported resource: {resource!r}")

        selector = data.get("selector")
        if not isinstance(selector, dict):
            selector = {}
        fields = data.get("fields")
        if not isinstance(fields, dict):
            fields = {}

        return self._normalize_event_operation(operation, selector, fields)

    def _normalize_event_operation(
        self,
        operation: str,
        selector: dict[str, Any],
        fields: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        if operation not in _EVENT_ACTIONS:
            raise ValueError(f"unsupported event operation: {operation!r}")

        action_name = _EVENT_ACTIONS[operation]
        event_type = selector.get("event_type") or fields.get("event_type")

        if operation == "create":
            if event_type not in _EVENT_TYPES:
                raise ValueError(f"unsupported event_type: {event_type!r}")
            if event_type in ("assignment", "life_event") and not fields.get("title"):
                raise ValueError("fields must include title")
            if event_type == "course_session" and not fields.get("course_name"):
                raise ValueError("fields must include course_name for course_session")
        elif operation in ("update", "delete"):
            if selector.get("id") is None:
                raise ValueError("selector must include id for event update/delete")
            if event_type not in _EVENT_TYPES:
                raise ValueError(f"unsupported event_type: {event_type!r}")

        payload = {
            "operation": operation,
            "resource": "event",
            "selector": selector,
            "fields": fields,
        }
        return action_name, payload
