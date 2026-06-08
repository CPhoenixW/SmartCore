from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.operations.parser import ParsedOperation

_SUPPORTED_RESOURCES = frozenset({"event"})
_SUPPORTED_OPERATIONS = frozenset({"create", "read", "update", "delete", "query"})
_EVENT_TYPES = frozenset({"course", "plan", "schedule", "deadline"})
_LEGACY_EVENT_TYPES = frozenset({"assignment", "life_event", "course_session"})
_ACCEPTED_EVENT_TYPES = _EVENT_TYPES | _LEGACY_EVENT_TYPES
_EVENT_ACTIONS = {
    "create": "create_event",
    "update": "update_event",
    "delete": "delete_event",
    "query": "query_event",
}
_SUPPORTED_ACTIONS = frozenset(_EVENT_ACTIONS.values())

_SYSTEM_PROMPT = """\
你是 SmartCore 个人调度助手的语义解析器。将用户的自然语言转为 JSON Action。

只返回一个 JSON 对象，不要 markdown 代码块，不要额外说明。

Action 结构：
- action: create_event | query_event | update_event | delete_event
- payload: 依 action 变化
- confidence: 0 到 1
- needs_confirmation: query_event 必须 false；create_event/update_event/delete_event 必须 true

公开 event_type 只能是 course、plan、schedule、deadline 之一。
不要输出已废弃的旧事件类型名称。
不要使用数据库 id 作为查询/修改/删除句柄。

create_event.payload.event:
- event_type: course/plan/schedule/deadline
- title, start_at, end_at, location, notes
- course/plan 需要 start_at 和 end_at；缺省 end_at 时由系统默认 start_at + 1 小时
- schedule/deadline 需要 start_at；可省略 reminders，系统默认在开始前 30 和 15 分钟提醒

query_event.payload:
- filter 必须包含 event_type、status、limit
- 当用户话里出现任何时间范围或相对时间词，filter 必须包含 time_range
- time_range 必须是半开区间 {"start": ISO8601, "end": ISO8601}
- 相对时间按当前时间和 Asia/Shanghai 解释：
  - 今早/早上/上午 = 今天 06:00 到 12:00
  - 中午 = 今天 11:00 到 14:00
  - 下午 = 今天 12:00 到 18:00
  - 今晚/晚上/今夜 = 今天 18:00 到次日 00:00
  - 今天/今日/今儿 = 今天 00:00 到次日 00:00
  - 明早 = 明天 06:00 到 12:00
  - 明天/明日 = 明天 00:00 到后天 00:00
- status 默认 ["pending","active"]，limit 默认 50
- semantic.target_description: 可选语义提示

update_event.payload:
- selector: mode=semantic_ref, refs(可留空由后端候选), filter, target_description
- patch: 如 start_at、end_at、title、location
- 如果用户原话包含时间范围，selector.filter 必须包含 time_range

delete_event.payload:
- selector: mode=semantic_ref, refs(可留空), allow_multiple, filter, target_description
- 如果用户原话包含时间范围，selector.filter 必须包含 time_range

当用户说“提醒我……”并给出时间时，输出 create_event + schedule。
当用户提到作业截止/DDL 时，输出 create_event + deadline。
当用户提到课程时间段时，输出 create_event + course。
当用户提到计划块/复习/安排时段时，输出 create_event + plan。

示例：
用户输入“今早有啥安排”，当前时间 2026-06-08T09:58:07+08:00，应输出：
{"action":"query_event","payload":{"filter":{"event_type":"all","status":["pending","active"],"limit":50,"time_range":{"start":"2026-06-08T06:00:00+08:00","end":"2026-06-08T12:00:00+08:00"}}},"confidence":0.9,"needs_confirmation":false}
"""

_SELECT_SYSTEM_PROMPT = """\
你是 SmartCore 事件候选选择器。根据用户原话、操作类型、补丁摘要和候选短列表，选择目标事件。

只返回 JSON：
{
  "match_status": "single | multiple | ambiguous | none",
  "selected_refs": ["c1"],
  "confidence": 0.0-1.0,
  "reason": "简短原因"
}

规则：
- 只能从给定候选里的 ref 选择，不能编造 ref，不能使用数据库 id。
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
        if isinstance(payload.get("action"), str):
            payload = {**payload, "source": source, "raw_text": text}
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
                    str(item.get("ref", "")),
                    str(item.get("event_type", "")),
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
        selected_refs = data.get("selected_refs")
        if not isinstance(selected_refs, list):
            selected_refs = []
        selected_ids = data.get("selected_ids")
        if not isinstance(selected_ids, list):
            selected_ids = []
        return {
            "match_status": data.get("match_status", "none"),
            "selected_refs": selected_refs,
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
        if "action" in data:
            return self._normalize_action_protocol(data)
        if "operation" in data:
            return self._normalize_unified_operation(data)
        raise ValueError("operation or action is required")

    def _normalize_action_protocol(
        self, data: dict[str, Any]
    ) -> tuple[str, dict[str, Any]]:
        action_name = data.get("action")
        if action_name not in _SUPPORTED_ACTIONS:
            raise ValueError(f"unsupported action: {action_name!r}")

        payload_body = data.get("payload")
        if not isinstance(payload_body, dict):
            raise ValueError("payload must be an object")

        if action_name == "create_event":
            event = payload_body.get("event")
            if not isinstance(event, dict):
                raise ValueError("create_event payload must include event")
            event_type = event.get("event_type")
            if event_type not in _EVENT_TYPES:
                raise ValueError(f"unsupported event_type: {event_type!r}")
        elif action_name == "query_event":
            filter_payload = payload_body.get("filter")
            if not isinstance(filter_payload, dict):
                raise ValueError("query_event payload must include filter")
        elif action_name == "update_event":
            selector = payload_body.get("selector")
            patch = payload_body.get("patch")
            if not isinstance(selector, dict) or not isinstance(patch, dict):
                raise ValueError(
                    "update_event payload must include selector and patch"
                )
        elif action_name == "delete_event":
            selector = payload_body.get("selector")
            if not isinstance(selector, dict):
                raise ValueError("delete_event payload must include selector")

        return action_name, {"action": action_name, "payload": payload_body}

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
            if event_type not in _ACCEPTED_EVENT_TYPES:
                raise ValueError(f"unsupported event_type: {event_type!r}")
            title_required_types = (
                "assignment",
                "life_event",
                "deadline",
                "schedule",
                "plan",
            )
            if event_type in title_required_types and not fields.get("title"):
                raise ValueError("fields must include title")
            if event_type in ("course_session", "course") and not (
                fields.get("course_name") or fields.get("title")
            ):
                raise ValueError("fields must include course_name or title for course")
        elif operation in ("update", "delete"):
            if selector.get("id") is None:
                scope_keys = (
                    "event_type",
                    "time_range",
                    "target_description",
                    "status",
                    "max_candidates",
                    "refs",
                    "mode",
                )
                if not any(selector.get(key) is not None for key in scope_keys):
                    raise ValueError(
                        "selector must include id or candidate scope for event update/delete"
                    )
            elif event_type not in _ACCEPTED_EVENT_TYPES:
                raise ValueError(f"unsupported event_type: {event_type!r}")

        payload = {
            "operation": operation,
            "resource": "event",
            "selector": selector,
            "fields": fields,
        }
        return action_name, payload
