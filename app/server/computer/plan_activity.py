from __future__ import annotations

import re

_EXPLICIT_NON_COMPUTER_HINTS = (
    "无需电脑",
    "不需要电脑",
    "不用电脑",
    "离开电脑",
    "no computer",
    "without a computer",
)

_COMPUTER_ACTIVITY_HINTS = (
    "用电脑",
    "电脑工作",
    "写代码",
    "改代码",
    "代码审查",
    "编程",
    "开发",
    "调试",
    "测试",
    "部署",
    "提交代码",
    "写文档",
    "写报告",
    "写论文",
    "做ppt",
    "做幻灯片",
    "数据分析",
    "在线会议",
    "视频会议",
    "前端",
    "后端",
    "服务器",
    "终端",
    "computer",
    "laptop",
    "coding",
    "programming",
    "debug",
    "deploy",
    "spreadsheet",
    "presentation",
    "online meeting",
    "video meeting",
)

_NON_COMPUTER_ACTIVITY_HINTS = (
    "吃饭",
    "早饭",
    "早餐",
    "午饭",
    "午餐",
    "晚饭",
    "晚餐",
    "夜宵",
    "用餐",
    "做饭",
    "休息",
    "午睡",
    "睡觉",
    "睡眠",
    "洗澡",
    "洗漱",
    "通勤",
    "坐地铁",
    "乘地铁",
    "坐公交",
    "开车",
    "驾车",
    "骑车",
    "散步",
    "跑步",
    "健身",
    "游泳",
    "瑜伽",
    "锻炼",
    "打球",
    "打扫",
    "洗衣",
    "家务",
    "遛狗",
    "看病",
    "就医",
    "理发",
    "聚餐",
    "break",
    "lunch",
    "dinner",
    "breakfast",
    "nap",
    "sleep",
    "commute",
    "workout",
    "gym",
)


def _contains_hint(text: str, hint: str) -> bool:
    if hint.isascii():
        return re.search(rf"(?<![a-z0-9]){re.escape(hint)}(?![a-z0-9])", text) is not None
    return hint in text


def plan_computer_activity_expected(title: str, description: str | None = None) -> bool:
    """Return whether computer activity is a meaningful signal for a Plan.

    Ambiguous Plans preserve the existing reminder behavior. High-confidence life activities are
    excluded, while an explicit computer-work hint wins for mixed Plans such as "晚饭后写代码".
    """

    text = " ".join(part.strip() for part in (title, description or "") if part.strip()).casefold()
    if any(_contains_hint(text, hint) for hint in _EXPLICIT_NON_COMPUTER_HINTS):
        return False
    if any(_contains_hint(text, hint) for hint in _COMPUTER_ACTIVITY_HINTS):
        return True
    return not any(_contains_hint(text, hint) for hint in _NON_COMPUTER_ACTIVITY_HINTS)
