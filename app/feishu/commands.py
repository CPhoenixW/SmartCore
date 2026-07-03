from __future__ import annotations

import json
import re

GROUP_MENTION_PREFIX_PATTERN = re.compile(r"^(?:@_user_\d+\s*)+")


def format_help_message() -> str:
    return "\n".join(
        [
            "SmartCore 个人秘书支持自然语言，例如：",
            "• 今天有什么安排 / 今早有啥事",
            "• 明天有什么安排",
            "• 还有什么没做 / 本周 DDL",
            "• 今晚八点提醒我做程设作业",
            "• 添加作业：高数作业 2026-06-10 20:00",
            "• 添加事项：洗衣服",
            "创建、修改、删除类操作会先发送确认卡片。",
            "发送「帮助」查看本说明。",
        ]
    )


def normalize_message_text(text: str) -> str:
    """Strip leading Feishu group-chat mention tokens (e.g. @_user_1)."""
    return GROUP_MENTION_PREFIX_PATTERN.sub("", text.strip()).strip()


def extract_routing_context(event_payload: dict) -> tuple[dict[str, str], dict[str, str]]:
    """Extract chat and user routing fields from a Feishu event payload."""
    event = event_payload.get("event")
    if not isinstance(event, dict):
        return {}, {}

    chat: dict[str, str] = {}
    message = event.get("message")
    if isinstance(message, dict):
        for key in ("chat_id", "chat_type"):
            value = message.get(key)
            if isinstance(value, str) and value:
                chat[key] = value

    user: dict[str, str] = {}
    sender = event.get("sender")
    if isinstance(sender, dict):
        sender_type = sender.get("sender_type")
        if isinstance(sender_type, str) and sender_type:
            user["sender_type"] = sender_type
        sender_id = sender.get("sender_id")
        if isinstance(sender_id, dict):
            for key in ("open_id", "union_id", "user_id"):
                value = sender_id.get(key)
                if isinstance(value, str) and value:
                    user[key] = value

    return chat, user


def extract_message_text(event_payload: dict) -> tuple[str | None, str | None]:
    event = event_payload.get("event")
    if not isinstance(event, dict):
        return None, None
    message = event.get("message")
    if not isinstance(message, dict):
        return None, None
    if message.get("message_type") != "text":
        return message.get("message_id"), None
    raw_content = message.get("content")
    if not isinstance(raw_content, str):
        return message.get("message_id"), None
    try:
        content = json.loads(raw_content)
    except json.JSONDecodeError:
        return message.get("message_id"), None
    text = content.get("text")
    if not isinstance(text, str):
        return message.get("message_id"), None
    return message.get("message_id"), normalize_message_text(text)
