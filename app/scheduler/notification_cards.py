from __future__ import annotations

from typing import Any

from app.secretary.rules import DayPlan, PlanItem


def _format_plan_items_markdown(label: str, items: list[PlanItem]) -> str:
    if not items:
        return ""
    lines = [f"**{label}**"]
    for item in items:
        parts = []
        if item.time_label:
            parts.append(item.time_label)
        parts.append(item.title)
        detail = " ".join(parts)
        if item.location:
            detail = f"{detail} · {item.location}"
        if item.notes:
            detail = f"{detail}\n  _{item.notes}_"
        lines.append(f"- {detail}")
    return "\n".join(lines)


def _card(header_title: str, template: str, markdown: str) -> dict[str, Any]:
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": header_title},
            "template": template,
        },
        "elements": [
            {"tag": "markdown", "content": markdown},
        ],
    }


def build_daily_digest_card(plan: DayPlan) -> dict[str, Any]:
    sections = [
        _format_plan_items_markdown("课程", plan.courses),
        _format_plan_items_markdown("今日 DDL", plan.assignments),
        _format_plan_items_markdown("生活事项", plan.life_events),
        _format_plan_items_markdown("待安排", plan.unscheduled),
    ]
    body = "\n\n".join(section for section in sections if section)
    if not body:
        body = "今天暂无安排。"
    markdown = f"**日期**：{plan.target_date.isoformat()}\n\n{body}"
    return _card("今日晨报", "green", markdown)


def build_tomorrow_preview_card(plan: DayPlan) -> dict[str, Any]:
    sections = [
        _format_plan_items_markdown("课程", plan.courses),
        _format_plan_items_markdown("DDL", plan.assignments),
        _format_plan_items_markdown("生活事项", plan.life_events),
    ]
    body = "\n\n".join(section for section in sections if section)
    if not body:
        body = "明天暂无安排。"
    markdown = f"**日期**：{plan.target_date.isoformat()}\n\n{body}"
    return _card("明日预告", "blue", markdown)


def build_pre_class_card(
    *,
    course_name: str,
    start_time: str | None,
    end_time: str | None,
    location: str | None,
    minutes_until: int,
) -> dict[str, Any]:
    time_range = start_time or "即将"
    if start_time and end_time:
        time_range = f"{start_time}–{end_time}"
    lines = [
        f"**课程**：{course_name}",
        f"**时间**：{time_range}",
        f"**倒计时**：约 {minutes_until} 分钟后开始",
    ]
    if location:
        lines.append(f"**地点**：{location}")
    lines.append("\n请提前准备教材并预留通勤时间。")
    return _card("课前提醒", "orange", "\n".join(lines))


def build_ddl_card(
    *,
    title: str,
    due_label: str | None,
    kind: str,
    course_name: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    if kind == "eve":
        header = "DDL 提醒 · 明天截止"
        template = "yellow"
        lead = "这份作业明天就要交了，今晚建议收尾。"
    else:
        header = "DDL 提醒 · 今天截止"
        template = "red"
        lead = "这份作业今天截止，请尽快完成并提交。"
    lines = [f"**作业**：{title}", lead]
    if due_label:
        lines.append(f"**截止时间**：{due_label}")
    if course_name:
        lines.append(f"**课程**：{course_name}")
    if notes:
        lines.append(f"**备注**：{notes}")
    return _card(header, template, "\n".join(lines))


def build_event_reminder_card(
    *,
    title: str,
    event_type: str,
    scheduled_label: str,
    minutes_until: int,
    notes: str | None = None,
) -> dict[str, Any]:
    type_labels = {
        "schedule": "生活安排",
        "plan": "计划块",
        "deadline": "截止事项",
        "course": "课程",
    }
    label = type_labels.get(event_type, "事项")
    lines = [
        f"**{label}**：{title}",
        f"**时间**：{scheduled_label}",
        f"**倒计时**：约 {minutes_until} 分钟后",
    ]
    if notes:
        lines.append(f"**备注**：{notes}")
    return _card("事项提醒", "turquoise", "\n".join(lines))
