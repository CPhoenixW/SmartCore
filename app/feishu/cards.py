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
    elif event_type:
        detail_lines.append(f"事件类型：{event_type}")
    if event_type == "life_event":
        detail_lines.extend(
            _format_life_event_detail_lines(
                {k: v for k, v in fields.items() if k != "event_type"},
                tz,
            )
        )
    else:
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
