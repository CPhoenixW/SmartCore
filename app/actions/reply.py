from __future__ import annotations

from typing import Any


def format_result_reply(result: dict[str, Any]) -> str:
    action = result.get("action")
    status = result.get("status")
    data = result.get("data") or {}

    if action == "query_event":
        return _format_query_reply(data.get("events") or [])

    if status == "pending_confirmation":
        preview = data.get("preview") or data.get("event") or {}
        title = preview.get("title") or "新事件"
        return f"已生成待确认操作：{title}"

    if status == "applied":
        event = data.get("event") or {}
        title = event.get("title")
        if title:
            return f"已确认并执行：{title}"
        return "已确认并执行"

    if status == "failed":
        errors = result.get("errors") or []
        if errors:
            return f"执行失败：{errors[0]}"
        return "执行失败：未知错误"

    if status == "not_found":
        return "未找到匹配事件。"

    if status == "ambiguous":
        errors = result.get("errors") or []
        detail = errors[0] if errors else "目标不够明确"
        return f"无法确定目标事件：{detail}，请补充更多信息。"

    message_code = result.get("message_code") or ""
    if message_code:
        return message_code
    return "操作已完成。"


def _format_query_reply(events: list[dict]) -> str:
    lines = ["【事件查询】"]
    if not events:
        lines.append("暂无匹配事件。")
    else:
        for item in events:
            lines.append(f"- {item.get('title', '')}")
    return "\n".join(lines)
