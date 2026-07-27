from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

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


def _feishu_markdown(content: Any) -> str:
    """Adapt common GFM syntax to the subset supported by Feishu lark_md."""
    lines = str(content or "").splitlines()
    normalized: list[str] = []
    in_code_block = False
    for line in lines:
        if line.lstrip().startswith("```"):
            in_code_block = not in_code_block
            normalized.append(line)
            continue
        if not in_code_block:
            heading = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", line)
            if heading:
                line = f"**{heading.group(1).strip()}**"
            else:
                line = re.sub(r"^\s*>\s?", "", line)
        normalized.append(line)
    return "\n".join(normalized)


def _markdown(content: Any) -> dict[str, str]:
    return {"tag": "lark_md", "content": _feishu_markdown(content)}


_TABLE_SEPARATOR_CELL = re.compile(r"^:?-{3,}:?$")


def _table_cells(line: str) -> list[str]:
    """Split a Markdown table row while preserving escaped pipe characters."""

    source = line.strip()
    if source.startswith("|"):
        source = source[1:]
    if source.endswith("|") and not source.endswith(r"\|"):
        source = source[:-1]

    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for character in source:
        if escaped:
            current.append(character)
            escaped = False
        elif character == "\\":
            escaped = True
            current.append(character)
        elif character == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(character)
    cells.append("".join(current).strip())
    return cells


def _is_table_separator(line: str, column_count: int) -> bool:
    cells = _table_cells(line)
    return len(cells) == column_count and all(
        _TABLE_SEPARATOR_CELL.fullmatch(cell.replace(" ", "")) for cell in cells
    )


def _table_row(cells: list[str], weights: list[int], *, header: bool) -> dict[str, Any]:
    columns = []
    for index, cell in enumerate(cells):
        content = f"**{cell}**" if header and cell else cell or " "
        columns.append(
            {
                "tag": "column",
                "width": "weighted",
                "weight": weights[index],
                "vertical_align": "top",
                "elements": [{"tag": "div", "text": _markdown(content)}],
            }
        )
    return {
        "tag": "column_set",
        "flex_mode": "none",
        "background_style": "grey" if header else "default",
        "horizontal_spacing": "default",
        "columns": columns,
    }


def _table_elements(rows: list[list[str]]) -> list[dict[str, Any]]:
    column_count = len(rows[0])
    normalized = [
        row[:column_count] + [""] * max(0, column_count - len(row))
        for row in rows
    ]
    widths = [
        max(len(row[index]) for row in normalized)
        for index in range(column_count)
    ]
    smallest = max(1, min(widths))
    weights = [max(1, min(4, round(width / smallest))) for width in widths]
    return [
        _table_row(row, weights, header=index == 0)
        for index, row in enumerate(normalized)
    ]


def _message_elements(content: str) -> list[dict[str, Any]]:
    """Convert GFM tables into card columns; keep other Markdown unchanged."""

    lines = content.splitlines()
    elements: list[dict[str, Any]] = []
    markdown_lines: list[str] = []
    in_code_block = False

    def flush_markdown() -> None:
        text = "\n".join(markdown_lines).strip("\n")
        if text:
            elements.append({"tag": "div", "text": _markdown(text)})
        markdown_lines.clear()

    index = 0
    while index < len(lines):
        line = lines[index]
        if line.lstrip().startswith("```"):
            in_code_block = not in_code_block
            markdown_lines.append(line)
            index += 1
            continue

        header = _table_cells(line)
        has_table = (
            not in_code_block
            and "|" in line
            and len(header) >= 2
            and index + 1 < len(lines)
            and _is_table_separator(lines[index + 1], len(header))
        )
        if not has_table:
            markdown_lines.append(line)
            index += 1
            continue

        flush_markdown()
        rows = [header]
        index += 2
        while index < len(lines) and "|" in lines[index]:
            row = _table_cells(lines[index])
            if len(row) < 2:
                break
            rows.append(row)
            index += 1
        elements.extend(_table_elements(rows))

    flush_markdown()
    return elements or [{"tag": "div", "text": _markdown("")}]


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
        elements=_message_elements(content),
    )
