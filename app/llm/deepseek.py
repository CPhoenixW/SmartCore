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
- selector: 定位已有事件。精确修改/删除可含 id 和 event_type；语义查询/修改/删除可不含 id，
  改用 event_type、time_range、status、max_candidates、target_description 描述候选范围
- fields: 事件字段，如 title、course_name、due_at、scheduled_at、deadline_at、
  weekday、start_time、end_time、location、notes、reminder_lead_minutes
- confidence: 0 到 1 的浮点数
- needs_confirmation: 布尔值；query 应为 false，写操作应为 true

create + event + assignment: fields 含 event_type=assignment、title、due_at。
create + event + life_event: fields 含 event_type=life_event、title、scheduled_at 等。
create + event + course_session: fields 含 event_type=course_session、course_name、
weekday、start_time、end_time、location 等。
update/delete + event: 若已知 id，selector 含 id 和 event_type；否则 selector 用候选范围字段，
  至少包含 event_type、time_range、target_description、status、max_candidates 之一。
  对 update/delete/query，默认优先使用 event_type=all，不要过早收窄；仅当用户明确提到
  作业/课程/课/ coursework/homework/class/course 或某一事件类别时，才使用具体 event_type。
query + event: selector 或 fields 可含 event_type（all/assignment/life_event/course_session）、
  status、time_range、max_candidates、target_description。
  对 query，同样默认优先 event_type=all，除非用户明确限定事件类别。

当用户说“提醒我……”并给出时间时，必须输出 create + event + life_event，
不要输出 create + reminder；Reminder 是系统内部发送队列，不是用户直接创建的资源。
当用户想修改/删除提醒事项时，输出 update/delete + event + life_event，而不是 reminder。
"""

_SELECT_SYSTEM_PROMPT = """\
你是 SmartCore 事件候选选择器。根据用户原话、操作类型、补丁摘要和候选短列表，选择目标事件。

只返回 JSON：
{
  "match_status": "single | multiple | ambiguous | none",
  "selected_ids": [{"event_type": "...", "id": 1}],
  "confidence": 0.0-1.0,
  "reason": "简短原因"
}

规则：
- 只能从给定候选里选择，不能编造 id。
- query 可多选；update 通常应 single；delete 可为 single 或 multiple。
- 综合比较标题/语义/时间，不要选择无关或弱相关候选。
- 无法确定时返回 ambiguous 或 none，不要猜测。
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

    def select_candidates(
        self,
        *,
        raw_text: str,
        parsed: ParsedOperation,
        candidates: list[dict],
    ) -> dict[str, Any]:
        if not candidates:
            return {
                "match_status": "none",
                "selected_ids": [],
                "confidence": 0.0,
                "reason": "无候选事件",
            }

        candidate_lines = [
            " | ".join(
                [
                    f"{item['event_type']}#{item['id']}",
                    str(item.get("status", "")),
                    str(item.get("time_label", "")),
                    str(item.get("title", "")),
                ]
            )
            for item in candidates
        ]
        fields = parsed.payload.get("fields") or {}
        patch_summary = json.dumps(fields, ensure_ascii=False)
        user_content = (
            f"用户原话：{raw_text}\n"
            f"操作：{parsed.action_name}\n"
            f"补丁摘要：{patch_summary}\n"
            "候选：\n"
            + "\n".join(candidate_lines)
        )
        raw_content = self._call_selection_completions(user_content)
        data = self._parse_json_content(raw_content)
        selected_ids = data.get("selected_ids")
        if not isinstance(selected_ids, list):
            selected_ids = []
        return {
            "match_status": data.get("match_status", "none"),
            "selected_ids": selected_ids,
            "confidence": float(data.get("confidence", 0.0)),
            "reason": data.get("reason", ""),
        }

    def _call_selection_completions(self, user_content: str) -> str:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": _SELECT_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
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
                scope_keys = (
                    "event_type",
                    "time_range",
                    "target_description",
                    "status",
                    "max_candidates",
                )
                if not any(selector.get(key) is not None for key in scope_keys):
                    raise ValueError(
                        "selector must include id or candidate scope for event update/delete"
                    )
            elif event_type not in _EVENT_TYPES:
                raise ValueError(f"unsupported event_type: {event_type!r}")

        payload = {
            "operation": operation,
            "resource": "event",
            "selector": selector,
            "fields": fields,
        }
        return action_name, payload
