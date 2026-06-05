from __future__ import annotations

from typing import Any


def build_pending_operation_card(
    *,
    operation_id: int,
    raw_text: str,
    action_name: str,
    payload: dict,
    dashboard_base_url: str,
) -> dict[str, Any]:
    fields = payload.get("fields", {})
    title = fields.get("title", "")
    detail_lines = [
        f"原始命令：{raw_text}",
        f"操作：{action_name}",
        f"资源：{payload.get('resource', '')}",
    ]
    if title:
        detail_lines.append(f"标题：{title}")
    for key, value in fields.items():
        if key == "title" or value in (None, ""):
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
