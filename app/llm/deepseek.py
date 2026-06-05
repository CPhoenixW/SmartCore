from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.operations.parser import ParsedOperation

_SUPPORTED_LEGACY_ACTIONS = frozenset({"create_assignment", "create_life_event"})
_SUPPORTED_RESOURCES = frozenset({"assignment", "life_event", "reminder"})
_SUPPORTED_OPERATIONS = frozenset({"create", "read", "update", "cancel"})
_UNIFIED_WRITE_ACTIONS = {
    ("create", "assignment"): "create_assignment",
    ("create", "life_event"): "create_life_event",
    ("update", "reminder"): "update_reminder",
    ("cancel", "reminder"): "cancel_reminder",
}

_SYSTEM_PROMPT = """\
你是 SmartCore 个人调度助手的语义解析器。将用户的自然语言转为 JSON 操作草案。

只返回一个 JSON 对象，不要 markdown 代码块，不要额外说明。

优先使用统一协议字段：
- operation: create/read/update/cancel 之一
- resource: life_event、assignment 或 reminder
- selector: 定位已有资源，例如 {"id": 12}
- fields: 资源字段对象
- confidence: 0 到 1 的浮点数
- needs_confirmation: 布尔值，写操作应为 true

也兼容旧格式 action_name/resource/fields。

create + assignment: fields 含 title、due_at（ISO 8601 带时区）。
create + life_event: fields 含 title、scheduled_at、deadline_at、reminder_rule、notes、
reminder_lead_minutes；带计划时间的事项应输出 scheduled_at 和 reminder_lead_minutes，
若用户未指定提前多久提醒，reminder_lead_minutes 默认为 15。
当用户说“提醒我……”并给出时间时，必须输出 create + life_event，不要输出
create + reminder；Reminder 是系统内部发送队列，不是用户直接创建的资源。
update + reminder: selector 必须含 id，fields 含 scheduled_at（ISO 8601 带时区）。
cancel + reminder: selector 必须含 id，fields 可为空对象。
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
        if "operation" in data:
            return self._normalize_unified_operation(data)
        return self._normalize_legacy_operation(data)

    def _normalize_legacy_operation(
        self, data: dict[str, Any]
    ) -> tuple[str, dict[str, Any]]:
        action_name = data.get("action_name")
        if action_name not in _SUPPORTED_LEGACY_ACTIONS:
            raise ValueError(f"unsupported action_name: {action_name!r}")
        resource = data.get("resource")
        if resource not in _SUPPORTED_RESOURCES:
            raise ValueError(f"unsupported resource: {resource!r}")
        fields = data.get("fields")
        if not isinstance(fields, dict) or not fields.get("title"):
            raise ValueError("fields must include title")
        return action_name, {"resource": resource, "fields": fields}

    def _normalize_unified_operation(
        self, data: dict[str, Any]
    ) -> tuple[str, dict[str, Any]]:
        operation = data.get("operation")
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

        if operation == "create" and resource == "reminder":
            return self._normalize_create_reminder_as_life_event(selector, fields)

        action_key = (operation, resource)
        if action_key not in _UNIFIED_WRITE_ACTIONS:
            raise ValueError(f"unsupported operation/resource: {operation}/{resource}")
        action_name = _UNIFIED_WRITE_ACTIONS[action_key]

        if resource == "reminder" and operation in ("update", "cancel"):
            if selector.get("id") is None:
                raise ValueError("selector must include id for reminder update/cancel")
        if resource == "reminder" and operation == "update":
            if not fields.get("scheduled_at"):
                raise ValueError("fields must include scheduled_at for reminder update")
        if operation == "create" and not fields.get("title"):
            raise ValueError("fields must include title")

        payload = {
            "operation": operation,
            "resource": resource,
            "selector": selector,
            "fields": fields,
        }
        return action_name, payload

    def _normalize_create_reminder_as_life_event(
        self,
        selector: dict[str, Any],
        fields: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        normalized_fields = dict(fields)
        if not normalized_fields.get("title") and normalized_fields.get("content"):
            normalized_fields["title"] = normalized_fields["content"]
        if not normalized_fields.get("title"):
            raise ValueError("fields must include title")
        if not normalized_fields.get("scheduled_at"):
            raise ValueError("fields must include scheduled_at for reminder create")
        normalized_fields.setdefault("reminder_lead_minutes", 15)
        payload = {
            "operation": "create",
            "resource": "life_event",
            "selector": selector,
            "fields": normalized_fields,
        }
        return "create_life_event", payload
