from __future__ import annotations

from typing import Any, Iterable

_HEADER_TEMPLATES = {
    "blue",
    "wathet",
    "turquoise",
    "green",
    "yellow",
    "orange",
    "red",
    "carmine",
    "violet",
    "purple",
    "indigo",
    "grey",
}


def _plain_text(content: Any) -> dict[str, str]:
    return {"tag": "plain_text", "content": str(content or "")}


def _markdown(content: Any) -> dict[str, str]:
    return {"tag": "lark_md", "content": str(content or "")}


def _header(title: str, template: str) -> dict[str, Any]:
    normalized = template if template in _HEADER_TEMPLATES else "blue"
    return {
        "template": normalized,
        "title": _plain_text(title or "SmartCore"),
    }


def _base_card(
    *,
    title: str,
    template: str = "blue",
    elements: Iterable[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "config": {
            "wide_screen_mode": True,
            "enable_forward": True,
        },
        "header": _header(title, template),
        "elements": list(elements or []),
    }


def normalize_card(card: dict[str, Any]) -> dict[str, Any]:
    """Normalize card JSON to the stable interactive-message card shape.

    SmartCore previously accepted Card JSON 2.0 with ``body.elements`` while the
    Feishu message API path used by this project is most consistently compatible
    with the classic top-level ``elements`` shape. This adapter also accepts
    already-normalized cards without altering their semantics.
    """

    if not isinstance(card, dict):
        raise ValueError("card must be an object")

    normalized = dict(card)
    body = normalized.pop("body", None)
    normalized.pop("schema", None)

    if "elements" not in normalized and isinstance(body, dict):
        body_elements = body.get("elements")
        if isinstance(body_elements, list):
            normalized["elements"] = body_elements

    elements = normalized.get("elements")
    if not isinstance(elements, list):
        raise ValueError("card.elements must be an array")

    config = normalized.get("config")
    if not isinstance(config, dict):
        config = {}
    normalized["config"] = {
        "wide_screen_mode": bool(config.get("wide_screen_mode", True)),
        "enable_forward": bool(config.get("enable_forward", True)),
        **{
            key: value
            for key, value in config.items()
            if key not in {"wide_screen_mode", "enable_forward"}
        },
    }

    header = normalized.get("header")
    if not isinstance(header, dict):
        normalized["header"] = _header("SmartCore", "blue")
    else:
        title = header.get("title")
        if isinstance(title, str):
            header = {**header, "title": _plain_text(title)}
        elif not isinstance(title, dict):
            header = {**header, "title": _plain_text("SmartCore")}
        template = header.get("template")
        if template not in _HEADER_TEMPLATES:
            header = {**header, "template": "blue"}
        normalized["header"] = header

    return normalized


def build_query_result_card(
    *,
    title: str = "查询结果",
    summary: str | None = None,
    items: list[dict[str, Any]] | None = None,
    empty_text: str = "没有找到匹配的事项。",
) -> dict[str, Any]:
    rows = items or []
    elements: list[dict[str, Any]] = []
    if summary:
        elements.append({"tag": "markdown", "content": summary})
    if not rows:
        elements.append({"tag": "div", "text": _markdown(empty_text)})
    else:
        for index, item in enumerate(rows[:20]):
            item_title = str(item.get("title") or item.get("name") or "未命名事项")
            item_type = str(item.get("evtType") or item.get("type") or "event")
            status = str(item.get("stat") or item.get("status") or "")
            time_text = str(
                item.get("endTime")
                or item.get("stTime")
                or item.get("time")
                or ""
            )
            details = [f"**{item_title}**", f"类型：{item_type}"]
            if status:
                details.append(f"状态：{status}")
            if time_text:
                details.append(f"时间：{time_text}")
            elements.append({"tag": "div", "text": _markdown("\n".join(details))})
            if index < min(len(rows), 20) - 1:
                elements.append({"tag": "hr"})

    return _base_card(title=title, template="blue", elements=elements)


def build_operation_success_card(
    *,
    title: str = "操作成功",
    content: str | None = None,
    operation: str | None = None,
    event: dict[str, Any] | None = None,
) -> dict[str, Any]:
    lines: list[str] = []
    if content:
        lines.append(content)
    if operation:
        lines.append(f"操作：{operation}")
    if event:
        event_title = event.get("title") or event.get("name")
        if event_title:
            lines.append(f"事项：{event_title}")
        event_type = event.get("evtType") or event.get("type")
        if event_type:
            lines.append(f"类型：{event_type}")
        event_time = event.get("endTime") or event.get("stTime") or event.get("time")
        if event_time:
            lines.append(f"时间：{event_time}")
    if not lines:
        lines.append("操作已完成。")
    return _base_card(
        title=title,
        template="green",
        elements=[{"tag": "div", "text": _markdown("\n".join(lines))}],
    )


def build_reminder_card(
    *,
    evt_id: str,
    title: str,
    content: str,
    allow_done: bool = True,
    allow_snooze: bool = True,
) -> dict[str, Any]:
    elements: list[dict[str, Any]] = [
        {
            "tag": "div",
            "text": _markdown(content or title or "提醒"),
        }
    ]
    actions: list[dict[str, Any]] = []
    action_value = {"kind": "smartcoreReminder", "evtId": evt_id}
    if allow_done:
        actions.append(
            {
                "tag": "button",
                "text": _plain_text("已完成"),
                "type": "primary",
                "value": {**action_value, "action": "reminderDone"},
            }
        )
    if allow_snooze:
        actions.append(
            {
                "tag": "button",
                "text": _plain_text("延时 10 分钟"),
                "type": "default",
                "value": {**action_value, "action": "reminderSnooze10"},
            }
        )
    if actions:
        elements.append({"tag": "action", "actions": actions})
    return _base_card(
        title=title or "提醒",
        template="orange",
        elements=elements,
    )


def build_message_card(
    *,
    title: str = "SmartCore",
    content: str,
    template: str = "blue",
) -> dict[str, Any]:
    return _base_card(
        title=title,
        template=template,
        elements=[{"tag": "div", "text": _markdown(content)}],
    )
