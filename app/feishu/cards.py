from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.actions.protocol import default_reminder_times, parse_iso_datetime
from app.secretary.rules import DEFAULT_TZ

_OPERATION_LABELS: dict[tuple[str, str], str] = {
    ("create_event", "schedule"): "新增事项",
    ("create_event", "deadline"): "新增作业",
    ("create_event", "plan"): "新增计划",
    ("create_event", "course"): "新增课程",
    ("update_event", "schedule"): "修改事项",
    ("update_event", "deadline"): "修改作业",
    ("update_event", "plan"): "修改计划",
    ("update_event", "course"): "修改课程",
    ("delete_event", "schedule"): "删除事项",
    ("delete_event", "deadline"): "删除作业",
    ("delete_event", "plan"): "删除计划",
    ("delete_event", "course"): "删除课程",
}


def _format_local_datetime(value: object, tz: ZoneInfo) -> str | None:
    if not value:
        return None
    dt = parse_iso_datetime(value) if not isinstance(value, datetime) else value
    if dt is None:
        return None
    return dt.astimezone(tz).strftime("%Y-%m-%d %H:%M")


def _reminder_time_lines(start_at_raw: object, tz: ZoneInfo) -> list[str]:
    start_at = parse_iso_datetime(start_at_raw)
    if start_at is None:
        return []
    lines: list[str] = []
    for reminder_at in default_reminder_times(start_at):
        local = reminder_at.astimezone(tz)
        lines.append(f"提醒时间：{local.strftime('%Y-%m-%d %H:%M')}")
    return lines


def _normalize_card_payload(action_name: str, payload: dict) -> dict:
    inner = payload.get("payload") or {}
    if action_name == "create_event" and isinstance(inner.get("event"), dict):
        return {
            "fields": inner["event"],
            "selector": {},
            "selected_candidates": [],
        }
    normalized = {
        "fields": inner.get("patch") or {},
        "selector": inner.get("selector") or {},
    }
    if inner.get("selected_candidates"):
        normalized["selected_candidates"] = inner["selected_candidates"]
    return normalized


def _resolve_event_type(action_name: str, payload: dict) -> str | None:
    fields = payload.get("fields") or {}
    if fields.get("event_type"):
        return str(fields["event_type"])
    selected_candidates = payload.get("selected_candidates") or []
    if isinstance(selected_candidates, list) and selected_candidates:
        first = selected_candidates[0]
        if isinstance(first, dict) and first.get("event_type"):
            return str(first["event_type"])
    selector = payload.get("selector") or {}
    if selector.get("event_type"):
        return str(selector["event_type"])
    targets = selector.get("targets")
    if isinstance(targets, list) and targets:
        first = targets[0]
        if isinstance(first, dict) and first.get("event_type"):
            return str(first["event_type"])
    return None


def _resolve_item_title(action_name: str, payload: dict) -> str:
    fields = payload.get("fields") or {}
    if fields.get("title"):
        return str(fields["title"])
    selected_candidates = payload.get("selected_candidates") or []
    if isinstance(selected_candidates, list) and selected_candidates:
        first = selected_candidates[0]
        if isinstance(first, dict) and first.get("title"):
            return str(first["title"])
    return ""


def _resolve_operation_label(action_name: str, event_type: str | None) -> str:
    if event_type:
        label = _OPERATION_LABELS.get((action_name, event_type))
        if label:
            return label
    fallback = {
        "create_event": "新增",
        "update_event": "修改",
        "delete_event": "删除",
    }
    return fallback.get(action_name, action_name)


def _append_time_detail_lines(
    detail_lines: list[str],
    *,
    start_at_raw: object,
    end_at_raw: object,
    tz: ZoneInfo,
    include_reminders: bool,
) -> None:
    start_label = _format_local_datetime(start_at_raw, tz)
    if start_label:
        detail_lines.append(f"开始时间：{start_label}")
    end_label = _format_local_datetime(end_at_raw, tz)
    if end_label:
        detail_lines.append(f"结束时间：{end_label}")
    if include_reminders and start_at_raw:
        detail_lines.extend(_reminder_time_lines(start_at_raw, tz))


def _build_pending_detail_lines(
    action_name: str,
    payload: dict,
    tz: ZoneInfo,
) -> list[str]:
    fields = payload.get("fields") or {}
    selector = payload.get("selector") or {}
    selected_candidates = payload.get("selected_candidates") or []
    event_type = _resolve_event_type(action_name, payload)
    operation_label = _resolve_operation_label(action_name, event_type)

    detail_lines = [f"操作：{operation_label}"]
    if event_type:
        detail_lines.append(f"事件类型：{event_type}")

    if action_name == "delete_event":
        delete_items: list[dict] = []
        if isinstance(selected_candidates, list) and selected_candidates:
            delete_items = [item for item in selected_candidates if isinstance(item, dict)]
        elif isinstance(selector.get("targets"), list):
            delete_items = [item for item in selector["targets"] if isinstance(item, dict)]
        for item in delete_items:
            title = item.get("title") or "目标事件"
            detail_lines.append(f"事项名称：{title}")
            time_label = item.get("time_label")
            if time_label:
                detail_lines.append(f"开始时间：{time_label}")
        return detail_lines

    title = _resolve_item_title(action_name, payload)
    if title:
        detail_lines.append(f"事项名称：{title}")

    if action_name == "update_event":
        start_at_raw = fields.get("start_at") or fields.get("scheduled_at") or fields.get("due_at")
        end_at_raw = fields.get("end_at") or fields.get("deadline_at")
        include_reminders = event_type in {"schedule", "deadline", "plan"}
        _append_time_detail_lines(
            detail_lines,
            start_at_raw=start_at_raw,
            end_at_raw=end_at_raw,
            tz=tz,
            include_reminders=include_reminders,
        )
        return detail_lines

    start_at_raw = fields.get("start_at") or fields.get("scheduled_at") or fields.get("due_at")
    end_at_raw = fields.get("end_at") or fields.get("deadline_at")
    include_reminders = event_type in {"schedule", "deadline"}
    _append_time_detail_lines(
        detail_lines,
        start_at_raw=start_at_raw,
        end_at_raw=end_at_raw,
        tz=tz,
        include_reminders=include_reminders,
    )
    return detail_lines


def build_pending_operation_card(
    *,
    operation_id: int,
    raw_text: str,
    action_name: str,
    payload: dict,
    dashboard_base_url: str,
    tz: ZoneInfo = DEFAULT_TZ,
) -> dict[str, Any]:
    del raw_text
    normalized = _normalize_card_payload(action_name, payload)
    detail_lines = _build_pending_detail_lines(action_name, normalized, tz)
    modify_url = f"{dashboard_base_url.rstrip('/')}/pending-operations"

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"待确认操作 #{operation_id}"},
            "template": "blue",
        },
        "elements": [
            {
                "tag": "div",
                "text": {"tag": "plain_text", "content": "\n".join(detail_lines)},
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "确认"},
                        "type": "primary",
                        "value": {
                            "smartcore_action": "confirm_operation",
                            "operation_id": operation_id,
                        },
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "修改命令"},
                        "type": "default",
                        "url": modify_url,
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "拒绝"},
                        "type": "danger",
                        "value": {
                            "smartcore_action": "reject_operation",
                            "operation_id": operation_id,
                        },
                    },
                ],
            },
        ],
    }


def _build_query_event_detail_lines(events: list[dict[str, Any]]) -> list[str]:
    lines = [f"共 {len(events)} 项"]
    if not events:
        lines.append("暂无匹配安排。")
        return lines

    for item in events:
        if len(events) > 1:
            lines.append("")
        lines.append(f"事件类型：{item.get('event_type', '')}")
        title = item.get("title")
        if title:
            lines.append(f"事项名称：{title}")
        time_label = item.get("time_label")
        if time_label:
            lines.append(f"时间：{time_label}")
        location = item.get("location")
        if location:
            lines.append(f"地点：{location}")
    return lines


def build_query_event_card(events: list[dict[str, Any]]) -> dict[str, Any]:
    detail_lines = _build_query_event_detail_lines(events)
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "事件查询"},
            "template": "blue",
        },
        "elements": [
            {
                "tag": "div",
                "text": {"tag": "plain_text", "content": "\n".join(detail_lines)},
            }
        ],
    }


def build_operation_success_card(
    *,
    action_name: str,
    payload: dict,
    tz: ZoneInfo = DEFAULT_TZ,
) -> dict[str, Any]:
    del tz
    normalized = _normalize_card_payload(action_name, payload)
    event_type = _resolve_event_type(action_name, normalized)
    operation_label = _resolve_operation_label(action_name, event_type)
    title = _resolve_item_title(action_name, normalized)

    detail_lines = ["操作成功", f"操作：{operation_label}"]
    if title:
        detail_lines.append(f"事项名称：{title}")

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "操作成功"},
            "template": "green",
        },
        "elements": [
            {
                "tag": "div",
                "text": {"tag": "plain_text", "content": "\n".join(detail_lines)},
            }
        ],
    }
