from __future__ import annotations

from typing import Literal

from app.secretary.rules import DayPlan, PlanItem


def _format_items(label: str, items: list[PlanItem]) -> list[str]:
    if not items:
        return []
    lines = [label]
    for item in items:
        detail = item.title
        if item.time_label:
            detail = f"{item.time_label} {detail}"
        if item.location:
            detail = f"{detail} @ {item.location}"
        lines.append(f"- {detail}")
    return lines


def format_daily_digest(plan: DayPlan) -> str:
    lines = [f"【今日晨报】{plan.target_date.isoformat()}", ""]
    sections = [
        _format_items("课程", plan.courses),
        _format_items("今日 DDL", plan.assignments),
        _format_items("生活事项", plan.life_events),
        _format_items("待安排", plan.unscheduled),
    ]
    for section in sections:
        if section:
            lines.extend(section)
            lines.append("")
    if len(lines) == 2:
        lines.append("今天暂无安排。")
    return "\n".join(lines).rstrip()


def format_tomorrow_preview(plan: DayPlan) -> str:
    lines = [f"【明日预告】{plan.target_date.isoformat()}", ""]
    sections = [
        _format_items("课程", plan.courses),
        _format_items("DDL", plan.assignments),
        _format_items("生活事项", plan.life_events),
    ]
    for section in sections:
        if section:
            lines.extend(section)
            lines.append("")
    if len(lines) == 2:
        lines.append("明天暂无安排。")
    return "\n".join(lines).rstrip()


def format_pre_class_message(
    *,
    course_name: str,
    start_time: str | None,
    location: str | None,
) -> str:
    time_part = start_time or "即将"
    lines = [f"【课前提醒】{time_part} 开始：{course_name}"]
    if location:
        lines.append(f"地点：{location}")
    return "\n".join(lines)


def format_ddl_message(
    *,
    title: str,
    due_label: str | None,
    kind: Literal["eve", "today"],
) -> str:
    if kind == "eve":
        header = "【DDL 提醒】明天截止"
    else:
        header = "【DDL 提醒】今天截止"
    lines = [header, title]
    if due_label:
        lines.append(f"截止时间：{due_label}")
    return "\n".join(lines)
