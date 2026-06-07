from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.secretary.rules import DEFAULT_TZ


def _format_life_event_detail_lines(fields: dict, tz: ZoneInfo) -> list[str]:
    lines: list[str] = []
    title = fields.get("title")
    if title:
        lines.append(f"事项：{title}")

    scheduled_at_raw = fields.get("scheduled_at")
    reminder_lead = fields.get("reminder_lead_minutes")
    if scheduled_at_raw:
        scheduled_at = datetime.fromisoformat(str(scheduled_at_raw))
        if scheduled_at.tzinfo is None:
            scheduled_at = scheduled_at.replace(tzinfo=tz)
        local_scheduled = scheduled_at.astimezone(tz)
        lines.append(f"计划时间：{local_scheduled.strftime('%Y-%m-%d %H:%M')}")
        if reminder_lead is not None:
            try:
                lead_minutes = int(reminder_lead)
            except (TypeError, ValueError):
                lead_minutes = None
            if lead_minutes is not None:
                reminder_at = local_scheduled - timedelta(minutes=lead_minutes)
                lines.append(f"提醒时间：{reminder_at.strftime('%Y-%m-%d %H:%M')}")
                lines.append(f"提前 {lead_minutes} 分钟")

    for key, value in fields.items():
        if key in {"title", "scheduled_at", "reminder_lead_minutes"} or value in (None, ""):
            continue
        lines.append(f"{key}：{value}")
    return lines


def _format_local_datetime(value: object, tz: ZoneInfo) -> str | None:
    if not value:
        return None
    dt = datetime.fromisoformat(str(value))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(tz).strftime("%Y-%m-%d %H:%M")


def _format_update_detail_lines(payload: dict, tz: ZoneInfo) -> list[str]:
    fields = payload.get("fields") or {}
    selected_candidates = payload.get("selected_candidates")
    lines: list[str] = []
    if isinstance(selected_candidates, list) and selected_candidates:
        lines.append("将修改：")
        for item in selected_candidates:
            label = item.get("title") or f"{item.get('event_type')}#{item.get('id')}"
            lines.append(f"- {label}")
            time_label = item.get("time_label")
            if time_label:
                lines.append(f"原计划时间：{time_label}")

    scheduled_at = _format_local_datetime(fields.get("scheduled_at"), tz)
    if scheduled_at:
        lines.append(f"新计划时间：{scheduled_at}")
        reminder_lead = fields.get("reminder_lead_minutes", 15)
        try:
            lead_minutes = int(reminder_lead)
        except (TypeError, ValueError):
            lead_minutes = None
        if lead_minutes is not None:
            dt = datetime.fromisoformat(str(fields["scheduled_at"]))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=tz)
            reminder_at = dt.astimezone(tz) - timedelta(minutes=lead_minutes)
            lines.append(f"新提醒时间：{reminder_at.strftime('%Y-%m-%d %H:%M')}")

    due_at = _format_local_datetime(fields.get("due_at"), tz)
    if due_at:
        lines.append(f"新截止时间：{due_at}")
    deadline_at = _format_local_datetime(fields.get("deadline_at"), tz)
    if deadline_at:
        lines.append(f"新截止/结束时间：{deadline_at}")
    if fields.get("title"):
        lines.append(f"新标题：{fields['title']}")
    if fields.get("notes"):
        lines.append(f"新备注：{fields['notes']}")
    return lines


def build_pending_operation_card(
    *,
    operation_id: int,
    raw_text: str,
    action_name: str,
    payload: dict,
    dashboard_base_url: str,
    tz: ZoneInfo = DEFAULT_TZ,
) -> dict[str, Any]:
    fields = payload.get("fields", {})
    selector = payload.get("selector") or {}
    title = fields.get("title", "")
    event_type = fields.get("event_type")
    detail_lines = [
        f"原始命令：{raw_text}",
        f"操作：{action_name}",
        f"资源：{payload.get('resource', '')}",
    ]
    selected_candidates = payload.get("selected_candidates")
    delete_targets = selector.get("targets")
    if action_name == "delete_event" and (
        isinstance(selected_candidates, list) and selected_candidates
        or isinstance(delete_targets, list) and delete_targets
    ):
        detail_lines.append("将删除：")
        if isinstance(selected_candidates, list) and selected_candidates:
            for item in selected_candidates:
                label = item.get("title") or f"{item.get('event_type')}#{item.get('id')}"
                detail_lines.append(f"- {label}")
        elif isinstance(delete_targets, list):
            for item in delete_targets:
                if isinstance(item, dict):
                    detail_lines.append(
                        f"- {item.get('event_type')}#{item.get('id')}"
                    )
    elif action_name == "update_event":
        detail_lines.extend(_format_update_detail_lines(payload, tz))
    elif event_type:
        detail_lines.append(f"事件类型：{event_type}")
    if action_name != "update_event" and event_type == "life_event":
        detail_lines.extend(
            _format_life_event_detail_lines(
                {k: v for k, v in fields.items() if k != "event_type"},
                tz,
            )
        )
    elif action_name != "update_event":
        if title:
            detail_lines.append(f"标题：{title}")
        for key, value in fields.items():
            if key in {"title", "event_type"} or value in (None, ""):
                continue
            detail_lines.append(f"{key}：{value}")

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
