from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.db import crud
from app.db.models import (
    Assignment,
    AssignmentStatus,
    LifeEvent,
    LifeEventStatus,
    Reminder,
    ReminderStatus,
)
from app.scheduler.daily_digest import format_daily_digest, format_tomorrow_preview
from app.secretary.planner import build_today_plan, build_tomorrow_plan
from app.secretary.rules import DEFAULT_TZ, format_datetime
from app.secretary.timetable import local_day_bounds

COMMAND_TODAY = "today"
COMMAND_TOMORROW = "tomorrow"
COMMAND_WEEKLY_DDL = "weekly_ddl"
COMMAND_ADD_ASSIGNMENT = "add_assignment"
COMMAND_ADD_LIFE_EVENT = "add_life_event"
COMMAND_COMPLETE = "complete"
COMMAND_CONFIRM_OPERATION = "confirm_operation"
COMMAND_REJECT_OPERATION = "reject_operation"
COMMAND_REMINDERS = "reminders"
COMMAND_CANCEL_REMINDER = "cancel_reminder"
COMMAND_UPDATE_REMINDER = "update_reminder"
COMMAND_HELP = "help"

REMINDER_UPDATE_PATTERN = re.compile(r"^(?P<id>\d+)\s+(?P<datetime>.+)$")
DATE_PATTERN = re.compile(
    r"^(?P<title>.+?)\s+(?P<date>\d{4}-\d{2}-\d{2}(?:[ T]\d{1,2}:\d{2})?)$"
)
GROUP_MENTION_PREFIX_PATTERN = re.compile(r"^(?:@_user_\d+\s*)+")


@dataclass(frozen=True)
class ParsedCommand:
    name: str
    args: str = ""


def format_help_message() -> str:
    return "\n".join(
        [
            "可用命令：",
            "今日 — 查看今日计划",
            "明日 — 查看明日计划",
            "本周DDL — 查看本周待交作业",
            "添加作业 <标题> [YYYY-MM-DD] — 添加作业",
            "添加事项 <标题> — 添加生活事项",
            "完成 <标题> — 标记作业或事项为已完成",
            "提醒队列 — 查看待发送/已发送提醒",
            "取消提醒 <编号> — 取消待发送提醒",
            "修改提醒 <编号> <YYYY-MM-DD HH:MM> — 修改待发送提醒时间",
            "帮助 — 显示本说明",
        ]
    )


def normalize_message_text(text: str) -> str:
    """Strip leading Feishu group-chat mention tokens (e.g. @_user_1)."""
    return GROUP_MENTION_PREFIX_PATTERN.sub("", text.strip()).strip()


def parse_command(text: str) -> ParsedCommand:
    normalized = text.strip()
    if not normalized:
        return ParsedCommand(COMMAND_HELP)

    if normalized in {"今日", "今天"}:
        return ParsedCommand(COMMAND_TODAY)
    if normalized in {"明日", "明天"}:
        return ParsedCommand(COMMAND_TOMORROW)
    if normalized in {"本周DDL", "本周ddl", "本周 DDL"}:
        return ParsedCommand(COMMAND_WEEKLY_DDL)
    if normalized in {"提醒队列", "提醒", "提醒列表"}:
        return ParsedCommand(COMMAND_REMINDERS)
    if normalized in {"帮助", "help", "?"}:
        return ParsedCommand(COMMAND_HELP)

    if normalized.startswith("添加作业"):
        args = normalized.removeprefix("添加作业").strip()
        if args:
            return ParsedCommand(COMMAND_ADD_ASSIGNMENT, args)
    if normalized.startswith("添加事项"):
        args = normalized.removeprefix("添加事项").strip()
        if args:
            return ParsedCommand(COMMAND_ADD_LIFE_EVENT, args)
    if normalized.startswith("完成"):
        args = normalized.removeprefix("完成").strip()
        if args:
            return ParsedCommand(COMMAND_COMPLETE, args)
    if normalized.startswith("确认"):
        args = normalized.removeprefix("确认").strip()
        if args:
            return ParsedCommand(COMMAND_CONFIRM_OPERATION, args)
    if normalized.startswith("拒绝"):
        args = normalized.removeprefix("拒绝").strip()
        if args:
            return ParsedCommand(COMMAND_REJECT_OPERATION, args)
    if normalized.startswith("取消提醒"):
        args = normalized.removeprefix("取消提醒").strip()
        if args:
            return ParsedCommand(COMMAND_CANCEL_REMINDER, args)
    if normalized.startswith("修改提醒"):
        args = normalized.removeprefix("修改提醒").strip()
        if args:
            return ParsedCommand(COMMAND_UPDATE_REMINDER, args)

    return ParsedCommand(COMMAND_HELP)


def _parse_assignment_args(args: str, tz: ZoneInfo) -> tuple[str, datetime | None]:
    match = DATE_PATTERN.match(args.strip())
    if not match:
        return args.strip(), None
    title = match.group("title").strip()
    raw_date = match.group("date").replace("T", " ")
    if len(raw_date) == 10:
        due_at = datetime.strptime(raw_date, "%Y-%m-%d").replace(tzinfo=tz)
    else:
        due_at = datetime.strptime(raw_date, "%Y-%m-%d %H:%M").replace(tzinfo=tz)
    return title, due_at


def _get_assignments_due_this_week(
    db: Session,
    target: date,
    tz: ZoneInfo,
) -> list[Assignment]:
    week_start = target - timedelta(days=target.weekday())
    week_end = week_start + timedelta(days=6)
    start, _ = local_day_bounds(week_start, tz)
    _, end = local_day_bounds(week_end, tz)
    return (
        db.query(Assignment)
        .filter(
            Assignment.due_at.isnot(None),
            Assignment.due_at >= start,
            Assignment.due_at < end,
            Assignment.status != AssignmentStatus.DONE.value,
            Assignment.status != AssignmentStatus.CANCELLED.value,
        )
        .order_by(Assignment.due_at.asc())
        .all()
    )


def _format_weekly_ddl(assignments: list[Assignment], tz: ZoneInfo) -> str:
    lines = ["【本周 DDL】", ""]
    if not assignments:
        lines.append("本周暂无待交作业。")
        return "\n".join(lines)
    for item in assignments:
        due_label = format_datetime(item.due_at, tz) if item.due_at else "未定"
        if item.due_at:
            due_date = item.due_at.astimezone(tz).date().isoformat()
            lines.append(f"- {due_date} {due_label} {item.title}")
        else:
            lines.append(f"- {item.title}")
    return "\n".join(lines)


def _find_open_assignment(db: Session, title: str) -> Assignment | None:
    return (
        db.query(Assignment)
        .filter(
            Assignment.title == title,
            Assignment.status != AssignmentStatus.DONE.value,
            Assignment.status != AssignmentStatus.CANCELLED.value,
        )
        .first()
    )


def _get_reminders_on_day(
    db: Session,
    target: date,
    tz: ZoneInfo,
    *,
    status: ReminderStatus | None = None,
) -> list[Reminder]:
    start, end = local_day_bounds(target, tz)
    query = db.query(Reminder).filter(
        Reminder.scheduled_at >= start,
        Reminder.scheduled_at < end,
    )
    if status is not None:
        query = query.filter(Reminder.status == status.value)
    return query.order_by(Reminder.scheduled_at.asc()).all()


def _format_reminder_line(reminder: Reminder, tz: ZoneInfo) -> str:
    time_label = reminder.scheduled_at.astimezone(tz).strftime("%H:%M")
    content = reminder.content or ""
    return f"- {time_label} {content}".rstrip()


def _format_pending_reminder_summary(
    reminders: list[Reminder],
    tz: ZoneInfo,
) -> list[str]:
    if not reminders:
        return []
    lines = ["待发送提醒"]
    for reminder in reminders:
        lines.append(_format_reminder_line(reminder, tz))
    return lines


def _format_reminder_queue(db: Session, tz: ZoneInfo) -> str:
    lines = ["【提醒队列】", ""]
    status_groups = [
        ("待发送", ReminderStatus.PENDING),
        ("已发送", ReminderStatus.SENT),
        ("失败", ReminderStatus.FAILED),
    ]
    has_any = False
    for label, status in status_groups:
        reminders = (
            db.query(Reminder)
            .filter(Reminder.status == status.value)
            .order_by(Reminder.scheduled_at.asc())
            .all()
        )
        if not reminders:
            continue
        has_any = True
        lines.append(f"{label}（{len(reminders)}）")
        for reminder in reminders:
            lines.append(_format_reminder_line(reminder, tz))
        lines.append("")
    if not has_any:
        lines.append("暂无提醒记录。")
    return "\n".join(lines).rstrip()


def _parse_reminder_id(args: str) -> tuple[int | None, str | None]:
    reminder_id_text = args.strip()
    if not reminder_id_text:
        return None, "请提供提醒编号，例如：取消提醒 12"
    if not reminder_id_text.isdigit():
        return None, "提醒编号必须是数字"
    return int(reminder_id_text), None


def _parse_reminder_update_args(
    args: str,
    tz: ZoneInfo,
) -> tuple[int | None, datetime | None, str | None]:
    args = args.strip()
    if not args:
        return None, None, "请提供提醒编号和时间，例如：修改提醒 12 2026-03-02 20:30"

    match = REMINDER_UPDATE_PATTERN.match(args)
    if not match:
        parts = args.split(maxsplit=1)
        if len(parts) == 1 and parts[0].isdigit():
            return int(parts[0]), None, "请提供新的发送时间，例如：修改提醒 12 2026-03-02 20:30"
        return None, None, "命令格式不正确，请使用：修改提醒 <编号> <YYYY-MM-DD HH:MM>"

    reminder_id = int(match.group("id"))
    raw_datetime = match.group("datetime").strip().replace("T", " ")
    try:
        if len(raw_datetime) == 10:
            scheduled_at = datetime.strptime(raw_datetime, "%Y-%m-%d").replace(tzinfo=tz)
        else:
            scheduled_at = datetime.strptime(raw_datetime, "%Y-%m-%d %H:%M").replace(tzinfo=tz)
    except ValueError:
        return reminder_id, None, "无法解析时间，请使用 YYYY-MM-DD HH:MM 格式"
    return reminder_id, scheduled_at, None


def _find_open_life_event(db: Session, title: str) -> LifeEvent | None:
    return (
        db.query(LifeEvent)
        .filter(
            LifeEvent.title == title,
            LifeEvent.status != LifeEventStatus.DONE.value,
            LifeEvent.status != LifeEventStatus.CANCELLED.value,
        )
        .first()
    )


def execute_command(
    db: Session,
    command: ParsedCommand,
    *,
    today: date | None = None,
    tz: ZoneInfo = DEFAULT_TZ,
    semester_start: date | None = None,
) -> str:
    target_date = today or date.today()

    if command.name == COMMAND_TODAY:
        plan = build_today_plan(
            db,
            today=target_date,
            tz=tz,
            semester_start=semester_start,
        )
        reply = format_daily_digest(plan)
        pending_reminders = _get_reminders_on_day(
            db,
            target_date,
            tz,
            status=ReminderStatus.PENDING,
        )
        summary = _format_pending_reminder_summary(pending_reminders, tz)
        if summary:
            reply = f"{reply}\n\n" + "\n".join(summary)
        return reply

    if command.name == COMMAND_TOMORROW:
        plan = build_tomorrow_plan(
            db,
            today=target_date,
            tz=tz,
            semester_start=semester_start,
        )
        reply = format_tomorrow_preview(plan)
        tomorrow = target_date + timedelta(days=1)
        pending_reminders = _get_reminders_on_day(
            db,
            tomorrow,
            tz,
            status=ReminderStatus.PENDING,
        )
        summary = _format_pending_reminder_summary(pending_reminders, tz)
        if summary:
            reply = f"{reply}\n\n" + "\n".join(summary)
        return reply

    if command.name == COMMAND_REMINDERS:
        return _format_reminder_queue(db, tz)

    if command.name == COMMAND_WEEKLY_DDL:
        assignments = _get_assignments_due_this_week(db, target_date, tz)
        return _format_weekly_ddl(assignments, tz)

    if command.name == COMMAND_ADD_ASSIGNMENT:
        title, due_at = _parse_assignment_args(command.args, tz)
        crud.create_assignment(db, title=title, due_at=due_at)
        if due_at:
            due_label = due_at.astimezone(tz).strftime("%Y-%m-%d %H:%M")
            return f"已添加作业：{title}（截止 {due_label}）"
        return f"已添加作业：{title}"

    if command.name == COMMAND_ADD_LIFE_EVENT:
        crud.create_life_event(db, title=command.args.strip())
        return f"已添加事项：{command.args.strip()}"

    if command.name == COMMAND_COMPLETE:
        title = command.args.strip()
        assignment = _find_open_assignment(db, title)
        if assignment:
            assignment.status = AssignmentStatus.DONE.value
            db.commit()
            return f"已完成作业：{title}"
        event = _find_open_life_event(db, title)
        if event:
            event.status = LifeEventStatus.DONE.value
            db.commit()
            return f"已完成事项：{title}"
        return f"未找到待完成的作业或事项：{title}"

    if command.name == COMMAND_CANCEL_REMINDER:
        reminder_id, error = _parse_reminder_id(command.args)
        if error:
            return error
        reminder = db.get(Reminder, reminder_id)
        if reminder is None:
            return f"未找到提醒 #{reminder_id}"
        if reminder.status == ReminderStatus.SENT.value:
            return f"提醒 #{reminder_id} 已发送，无法取消"
        if reminder.status == ReminderStatus.CANCELLED.value:
            return f"提醒 #{reminder_id} 已取消"
        if reminder.status not in (
            ReminderStatus.PENDING.value,
            ReminderStatus.FAILED.value,
        ):
            return f"提醒 #{reminder_id} 当前状态无法取消"
        reminder.status = ReminderStatus.CANCELLED.value
        db.commit()
        return f"已取消提醒 #{reminder_id}"

    if command.name == COMMAND_UPDATE_REMINDER:
        reminder_id, scheduled_at, error = _parse_reminder_update_args(command.args, tz)
        if error:
            return error
        reminder = db.get(Reminder, reminder_id)
        if reminder is None:
            return f"未找到提醒 #{reminder_id}"
        if reminder.status != ReminderStatus.PENDING.value:
            return f"提醒 #{reminder_id} 当前状态无法修改"
        reminder.scheduled_at = scheduled_at
        db.commit()
        time_label = scheduled_at.astimezone(tz).strftime("%H:%M")
        return f"已修改提醒 #{reminder_id}，新时间 {time_label}"

    return format_help_message()


def extract_message_text(event_payload: dict) -> tuple[str | None, str | None]:
    """Return (message_id, plain_text) from a Feishu message event payload."""
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
