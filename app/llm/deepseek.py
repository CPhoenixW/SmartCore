from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.operations.parser import ParsedOperation

_SUPPORTED_ACTIONS = frozenset({"create_assignment", "create_life_event"})
_SUPPORTED_RESOURCES = frozenset({"assignment", "life_event"})

_SYSTEM_PROMPT = """\
你是 SmartCore 个人调度助手的语义解析器。将用户的自然语言转为 JSON 操作草案。

只返回一个 JSON 对象，不要 markdown 代码块，不要额外说明。字段：
- action_name: create_assignment 或 create_life_event
- resource: assignment 或 life_event
- fields: 资源字段对象（至少包含 title）
- confidence: 0 到 1 的浮点数
- needs_confirmation: 布尔值，写操作应为 true

create_assignment 的 fields 可含 title、due_at（ISO 8601 带时区）。
create_life_event 的 fields 可含 title、scheduled_at、deadline_at、reminder_rule、notes、
reminder_lead_minutes。
当用户为带计划时间的事项请求提醒时，应输出 scheduled_at 和 reminder_lead_minutes；
若用户未指定提前多久提醒，reminder_lead_minutes 默认为 15。
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
        self._validate_operation(data)
        return ParsedOperation(
            source=source,
            raw_text=text,
            action_name=data["action_name"],
            payload={"resource": data["resource"], "fields": data["fields"]},
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

    def _validate_operation(self, data: dict[str, Any]) -> None:
        action_name = data.get("action_name")
        if action_name not in _SUPPORTED_ACTIONS:
            raise ValueError(f"unsupported action_name: {action_name!r}")
        resource = data.get("resource")
        if resource not in _SUPPORTED_RESOURCES:
            raise ValueError(f"unsupported resource: {resource!r}")
        fields = data.get("fields")
        if not isinstance(fields, dict) or not fields.get("title"):
            raise ValueError("fields must include title")
