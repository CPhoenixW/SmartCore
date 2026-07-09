from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Iterable, Literal, TypedDict
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.new_core.models import AppUser, EvtBase, PlanEvt, RemindEvt, newId, nowIso

_DEFAULT_TZ = ZoneInfo("Asia/Shanghai")
_MAX_OFFSET_MIN = 7 * 24 * 60
_CUSTOM_KIND_RE = re.compile(r"^custom_(start|end)_(\d+)m$")
_DEFAULT_PAIRS = {("start", 10), ("end", 10)}


class ReminderSpec(TypedDict):
    anchor: Literal["start", "end"]
    offsetMin: int


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_DEFAULT_TZ)
    return parsed.astimezone(_DEFAULT_TZ).replace(microsecond=0)


def _normalize_anchor(value: Any) -> Literal["start", "end"]:
    aliases = {
        "start": "start",
        "begin": "start",
        "开始": "start",
        "计划开始": "start",
        "end": "end",
        "finish": "end",
        "结束": "end",
        "计划结束": "end",
    }
    anchor = aliases.get(str(value or "start").strip().lower())
    if anchor not in {"start", "end"}:
        raise ValueError("reminder anchor must be start or end")
    return anchor


def normalize_extra_reminders(values: Iterable[dict[str, Any]] | None) -> list[ReminderSpec]:
    result: list[ReminderSpec] = []
    seen: set[tuple[str, int]] = set()
    for index, raw in enumerate(values or []):
        if not isinstance(raw, dict):
            raise ValueError(f"extraReminders[{index}] must be an object")
        anchor = _normalize_anchor(raw.get("anchor"))
        try:
            offset = int(raw.get("offsetMin", 0))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"extraReminders[{index}].offsetMin must be an integer") from exc
        if offset < 0 or offset > _MAX_OFFSET_MIN:
            raise ValueError(
                f"extraReminders[{index}].offsetMin must be between 0 and {_MAX_OFFSET_MIN}"
            )
        pair = (anchor, offset)
        if pair in _DEFAULT_PAIRS or pair in seen:
            continue
        seen.add(pair)
        result.append({"anchor": anchor, "offsetMin": offset})
    return result


def _kind(anchor: str, offset: int) -> str:
    return f"custom_{anchor}_{offset}m"


def _parse_kind(kind: str) -> ReminderSpec | None:
    match = _CUSTOM_KIND_RE.fullmatch(str(kind))
    if match is None:
        return None
    return {
        "anchor": match.group(1),
        "offsetMin": int(match.group(2)),
    }


def _plan_times(plan: PlanEvt) -> tuple[datetime, datetime]:
    start = _parse_datetime(plan.stTime)
    end = start + timedelta(minutes=max(1, int(plan.durationMin)))
    return start, end


def _trigger(plan: PlanEvt, spec: ReminderSpec) -> datetime:
    start, end = _plan_times(plan)
    anchor_time = start if spec["anchor"] == "start" else end
    return anchor_time - timedelta(minutes=spec["offsetMin"])


def _copy(
    *,
    plan_title: str,
    language: str,
    anchor: str,
    offset: int,
    target: datetime,
) -> tuple[str, str]:
    if language == "en":
        phase = "starts" if anchor == "start" else "ends"
        if offset == 0:
            return (
                f"{plan_title} · {phase} now",
                f"The plan {phase} now: {target.isoformat()}",
            )
        return (
            f"{plan_title} · {offset} min before it {phase}",
            f"The plan {phase} in {offset} minutes: {target.isoformat()}",
        )
    phase = "开始" if anchor == "start" else "结束"
    if offset == 0:
        return (
            f"{plan_title} · 现在{phase}",
            f"计划现在{phase}：{target.isoformat()}",
        )
    return (
        f"{plan_title} · {phase}前 {offset} 分钟",
        f"计划将在 {offset} 分钟后{phase}：{target.isoformat()}",
    )


def _language(db: Session, user_id: str) -> str:
    user = db.get(AppUser, user_id)
    return "en" if user is not None and user.language == "en" else "zh"


def _delete_reminder(db: Session, reminder: RemindEvt) -> None:
    base = db.get(EvtBase, reminder.evtId)
    db.delete(reminder)
    if base is not None:
        db.delete(base)


def list_extra_reminder_specs(db: Session, plan_evt_id: str) -> list[ReminderSpec]:
    rows = db.scalars(
        select(RemindEvt)
        .where(RemindEvt.planEvtId == plan_evt_id)
        .order_by(RemindEvt.triggerTime.asc())
    ).all()
    result: list[ReminderSpec] = []
    for row in rows:
        parsed = _parse_kind(row.remindKind)
        if parsed is not None:
            result.append(parsed)
    return result


def replace_extra_reminders(
    db: Session,
    plan_evt_id: str,
    values: Iterable[dict[str, Any]] | None,
    *,
    commit: bool = True,
) -> list[dict[str, Any]]:
    plan_base = db.get(EvtBase, plan_evt_id)
    plan = db.get(PlanEvt, plan_evt_id)
    if plan_base is None or plan is None:
        raise ValueError(f"plan not found: {plan_evt_id}")

    specs = normalize_extra_reminders(values)
    desired = {_kind(spec["anchor"], spec["offsetMin"]): spec for spec in specs}
    existing_rows = db.scalars(
        select(RemindEvt).where(RemindEvt.planEvtId == plan_evt_id)
    ).all()
    existing = {
        row.remindKind: row
        for row in existing_rows
        if _parse_kind(row.remindKind) is not None
    }

    for kind, row in existing.items():
        if kind not in desired:
            _delete_reminder(db, row)

    language = _language(db, plan_base.userId)
    start, end = _plan_times(plan)
    for kind, spec in desired.items():
        target = start if spec["anchor"] == "start" else end
        title, content = _copy(
            plan_title=plan_base.title,
            language=language,
            anchor=spec["anchor"],
            offset=spec["offsetMin"],
            target=target,
        )
        trigger = _trigger(plan, spec).isoformat()
        reminder = existing.get(kind)
        target_stat = "todo" if plan_base.stat == "todo" else "cancelled"
        if reminder is None:
            reminder_base = EvtBase(
                evtId=newId(),
                userId=plan_base.userId,
                title=title,
                desc=content,
                evtType="remind",
                prio=plan_base.prio,
                stat=target_stat,
                createdAt=nowIso(),
                updatedAt=nowIso(),
            )
            db.add(reminder_base)
            db.flush()
            db.add(
                RemindEvt(
                    evtId=reminder_base.evtId,
                    planEvtId=plan_evt_id,
                    remindKind=kind,
                    triggerTime=trigger,
                    offsetMin=spec["offsetMin"],
                    firedAt=None,
                )
            )
            continue

        reminder_base = db.get(EvtBase, reminder.evtId)
        changed = reminder.triggerTime != trigger
        reminder.triggerTime = trigger
        reminder.offsetMin = spec["offsetMin"]
        if changed:
            reminder.firedAt = None
        if reminder_base is not None:
            reminder_base.title = title
            reminder_base.desc = content
            reminder_base.prio = plan_base.prio
            reminder_base.stat = target_stat if reminder.firedAt is None else "done"
            reminder_base.updatedAt = nowIso()

    db.flush()
    if commit:
        db.commit()
    return [dict(spec) for spec in specs]


def sync_extra_reminders(
    db: Session,
    plan_evt_id: str,
    *,
    commit: bool = True,
) -> list[dict[str, Any]]:
    return replace_extra_reminders(
        db,
        plan_evt_id,
        list_extra_reminder_specs(db, plan_evt_id),
        commit=commit,
    )


def localized_reminder_message(
    db: Session,
    reminder: RemindEvt,
    plan_base: EvtBase,
) -> tuple[str, str]:
    plan = db.get(PlanEvt, reminder.planEvtId)
    if plan is None:
        return plan_base.title, plan_base.desc or plan_base.title

    custom = _parse_kind(reminder.remindKind)
    if custom is not None:
        anchor = custom["anchor"]
        offset = custom["offsetMin"]
    elif reminder.remindKind == "plan_end_10m":
        anchor, offset = "end", int(reminder.offsetMin or 10)
    else:
        anchor, offset = "start", int(reminder.offsetMin or 10)

    start, end = _plan_times(plan)
    target = start if anchor == "start" else end
    return _copy(
        plan_title=plan_base.title,
        language=_language(db, plan_base.userId),
        anchor=anchor,
        offset=offset,
        target=target,
    )
