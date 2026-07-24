from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.server.new_core import crud
from app.server.new_core.event_relations import get_event, sync_plan_reminders
from app.server.new_core.models import (
    ActLog,
    DdlEvt,
    DdlPlan,
    EvtBase,
    PlanEvt,
    RemindEvt,
    newId,
    nowIso,
)

_DEFAULT_TZ = ZoneInfo("Asia/Shanghai")
_ALLOWED_PLAN_ROLES = {"one_day_before", "one_hour_before", "manual"}


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_DEFAULT_TZ)
    return parsed.astimezone(_DEFAULT_TZ).replace(microsecond=0)


def default_ddl_plans(end_time: str) -> list[dict[str, Any]]:
    end_dt = _parse_datetime(end_time)
    return [
        {
            "planRole": "one_day_before",
            "stTime": (end_dt - timedelta(days=1)).isoformat(),
            "durationMin": 30,
            "sortOrder": 0,
        },
        {
            "planRole": "one_hour_before",
            "stTime": (end_dt - timedelta(hours=1)).isoformat(),
            "durationMin": 30,
            "sortOrder": 1,
        },
    ]


def _plan_title(ddl_title: str, role: str, index: int = 0) -> str:
    labels = {
        "one_day_before": "提前一天",
        "one_hour_before": "提前一小时",
        "manual": "关联计划",
    }
    suffix = labels.get(role, "关联计划")
    if role == "manual" and index > 0:
        suffix = f"关联计划 {index + 1}"
    return f"{ddl_title} · {suffix}"


def _normalize_plan_specs(
    ddl_title: str,
    plan_specs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    manual_index = 0
    for order, raw in enumerate(plan_specs):
        if not isinstance(raw, dict):
            raise ValueError(f"plans[{order}] must be an object")
        if raw.get("enabled", True) is False:
            continue
        role = str(raw.get("planRole") or raw.get("role") or "manual")
        if role not in _ALLOWED_PLAN_ROLES:
            raise ValueError(f"unsupported planRole: {role}")
        st_time = str(raw.get("stTime") or "").strip()
        if not st_time:
            raise ValueError(f"stTime required for plans[{order}]")
        duration = int(raw.get("durationMin") or 30)
        if duration <= 0:
            raise ValueError("durationMin must be greater than 0")
        title_index = manual_index if role == "manual" else 0
        if role == "manual":
            manual_index += 1
        normalized.append(
            {
                "planEvtId": str(raw.get("planEvtId") or raw.get("evtId") or "").strip() or None,
                "planRole": role,
                "stTime": _parse_datetime(st_time).isoformat(),
                "durationMin": duration,
                "title": str(raw.get("title") or _plan_title(ddl_title, role, title_index)).strip(),
                "desc": raw.get("desc") or "DDL 关联计划",
                "sortOrder": int(raw.get("sortOrder") if raw.get("sortOrder") is not None else order),
            }
        )
    return normalized


def _normalize_reminder_specs(
    ddl_title: str,
    reminder_specs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for order, raw in enumerate(reminder_specs):
        if not isinstance(raw, dict) or raw.get("enabled", True) is False:
            continue
        trigger_time = str(raw.get("triggerTime") or raw.get("at") or "").strip()
        if not trigger_time:
            raise ValueError(f"ddlReminders[{order}].triggerTime required")
        title = str(raw.get("title") or f"{ddl_title} · 提醒").strip()
        if not title:
            raise ValueError(f"ddlReminders[{order}].title required")
        priority = str(raw.get("prio") or raw.get("priority") or "high").lower()
        if priority not in {"low", "mid", "high"}:
            raise ValueError(f"ddlReminders[{order}].prio invalid")
        normalized.append({
            "remindEvtId": str(raw.get("remindEvtId") or raw.get("evtId") or "").strip() or None,
            "title": title,
            "desc": raw.get("desc") or "DDL 关联提醒",
            "triggerTime": _parse_datetime(trigger_time).isoformat(),
            "prio": priority,
        })
    return normalized


def _add_ddl_reminder(db: Session, *, ddl_id: str, ddl_base: EvtBase, spec: dict[str, Any], src: str) -> str:
    reminder_id = newId()
    now = nowIso()
    db.add(EvtBase(
        evtId=reminder_id, userId=ddl_base.userId, title=spec["title"], desc=spec["desc"],
        evtType="remind", prio=spec["prio"], stat="todo" if ddl_base.stat == "todo" else "cancelled",
        createdAt=now, updatedAt=now,
    ))
    db.add(RemindEvt(
        evtId=reminder_id, planEvtId=None, ddlEvtId=ddl_id, remindKind="ddl_linked",
        triggerTime=spec["triggerTime"], offsetMin=0, firedAt=None,
    ))
    db.add(ActLog(
        userId=ddl_base.userId, actorKind="system" if src == "api" else _actor_kind(src),
        actorId="ddl-reminder" if src == "api" else src, action="auto_create" if src == "api" else "create",
        targetKind="evt", targetId=reminder_id, result="ok",
    ))
    return reminder_id


def replace_ddl_reminders(db: Session, ddl_evt_id: str, reminders: list[dict[str, Any]], *, src: str = "api", commit: bool = True) -> dict[str, Any]:
    ddl_base = db.get(EvtBase, ddl_evt_id)
    ddl = db.get(DdlEvt, ddl_evt_id)
    if ddl_base is None or ddl is None:
        raise ValueError(f"ddl not found: {ddl_evt_id}")
    normalized = _normalize_reminder_specs(ddl_base.title, reminders)
    existing = {row.evtId: row for row in db.scalars(select(RemindEvt).where(RemindEvt.ddlEvtId == ddl_evt_id)).all()}
    retained: set[str] = set()
    for spec in normalized:
        reminder_id = spec["remindEvtId"]
        if reminder_id and reminder_id in existing:
            reminder = existing[reminder_id]
            base = db.get(EvtBase, reminder_id)
            if base is None:
                raise ValueError(f"linked reminder not found: {reminder_id}")
            base.title, base.desc, base.prio = spec["title"], spec["desc"], spec["prio"]
            base.stat = "todo" if ddl_base.stat == "todo" else "cancelled"
            base.updatedAt = nowIso()
            if reminder.triggerTime != spec["triggerTime"]:
                reminder.triggerTime, reminder.firedAt = spec["triggerTime"], None
            retained.add(reminder_id)
        else:
            retained.add(_add_ddl_reminder(db, ddl_id=ddl_evt_id, ddl_base=ddl_base, spec=spec, src=src))
    for reminder_id, reminder in existing.items():
        if reminder_id not in retained:
            base = db.get(EvtBase, reminder_id)
            db.delete(reminder)
            if base is not None:
                db.delete(base)
    db.flush()
    if commit:
        db.commit()
    return get_event(db, ddl_evt_id)


def _actor_kind(src: str) -> str:
    return "llm" if src in {"openclaw", "llm"} else "user"


def _add_plan(
    db: Session,
    *,
    ddl_id: str,
    ddl_base: EvtBase,
    spec: dict[str, Any],
    src: str,
) -> str:
    now = nowIso()
    plan_id = newId()
    plan_base = EvtBase(
        evtId=plan_id,
        userId=ddl_base.userId,
        title=spec["title"],
        desc=spec["desc"],
        evtType="plan",
        prio=ddl_base.prio,
        stat="todo" if ddl_base.stat == "todo" else "cancelled",
        createdAt=now,
        updatedAt=now,
    )
    db.add(plan_base)
    db.add(
        PlanEvt(
            evtId=plan_id,
            stTime=spec["stTime"],
            durationMin=spec["durationMin"],
        )
    )
    db.flush()
    db.add(
        DdlPlan(
            ddlEvtId=ddl_id,
            planEvtId=plan_id,
            planRole=spec["planRole"],
            sortOrder=spec["sortOrder"],
        )
    )
    sync_plan_reminders(db, plan_id)
    db.add(
        ActLog(
            userId=ddl_base.userId,
            actorKind="system" if src == "api" else _actor_kind(src),
            actorId="ddl-plan" if src == "api" else src,
            action="auto_create" if src == "api" else "create",
            targetKind="planEvt",
            targetId=plan_id,
            result="ok",
        )
    )
    return plan_id


def _delete_plan_tree(db: Session, plan_id: str) -> None:
    reminder_ids = list(
        db.scalars(select(RemindEvt.evtId).where(RemindEvt.planEvtId == plan_id)).all()
    )
    for reminder_id in reminder_ids:
        reminder = db.get(RemindEvt, reminder_id)
        reminder_base = db.get(EvtBase, reminder_id)
        if reminder is not None:
            db.delete(reminder)
        if reminder_base is not None:
            db.delete(reminder_base)
    link = db.scalar(select(DdlPlan).where(DdlPlan.planEvtId == plan_id))
    if link is not None:
        db.delete(link)
    plan = db.get(PlanEvt, plan_id)
    base = db.get(EvtBase, plan_id)
    if plan is not None:
        db.delete(plan)
    if base is not None:
        db.delete(base)


def replace_ddl_plans(
    db: Session,
    ddl_evt_id: str,
    plans: list[dict[str, Any]],
    *,
    src: str = "api",
    commit: bool = True,
) -> dict[str, Any]:
    ddl_base = db.get(EvtBase, ddl_evt_id)
    ddl = db.get(DdlEvt, ddl_evt_id)
    if ddl_base is None or ddl is None:
        raise ValueError(f"ddl not found: {ddl_evt_id}")
    normalized = _normalize_plan_specs(ddl_base.title, plans)
    existing_links = db.scalars(
        select(DdlPlan).where(DdlPlan.ddlEvtId == ddl_evt_id)
    ).all()
    existing = {link.planEvtId: link for link in existing_links}
    retained: set[str] = set()

    for spec in normalized:
        plan_id = spec.get("planEvtId")
        if plan_id and plan_id in existing:
            link = existing[plan_id]
            plan_base = db.get(EvtBase, plan_id)
            plan = db.get(PlanEvt, plan_id)
            if plan_base is None or plan is None:
                raise ValueError(f"linked plan not found: {plan_id}")
            changed = plan.stTime != spec["stTime"] or int(plan.durationMin) != int(spec["durationMin"])
            plan_base.title = spec["title"]
            plan_base.desc = spec["desc"]
            plan_base.prio = ddl_base.prio
            if ddl_base.stat != "todo" and plan_base.stat == "todo":
                plan_base.stat = "cancelled"
            plan_base.updatedAt = nowIso()
            plan.stTime = spec["stTime"]
            plan.durationMin = spec["durationMin"]
            link.planRole = spec["planRole"]
            link.sortOrder = spec["sortOrder"]
            sync_plan_reminders(db, plan_id, reset_fired=changed)
            retained.add(plan_id)
            continue
        new_id = _add_plan(
            db,
            ddl_id=ddl_evt_id,
            ddl_base=ddl_base,
            spec=spec,
            src=src,
        )
        retained.add(new_id)

    for plan_id in existing:
        if plan_id not in retained:
            _delete_plan_tree(db, plan_id)

    db.flush()
    if commit:
        db.commit()
    return get_event(db, ddl_evt_id)


def create_ddl_event(
    db: Session,
    *,
    title: str,
    endTime: str,
    hardDdl: bool = False,
    desc: str | None = None,
    prio: str = "high",
    plans: list[dict[str, Any]] | None = None,
    ddlReminders: list[dict[str, Any]] | None = None,
    userId: str = crud.DEFAULT_USER_ID,
    src: str = "api",
) -> dict[str, Any]:
    clean_title = str(title).strip()
    if not clean_title:
        raise ValueError("title required")
    normalized_end = _parse_datetime(endTime).isoformat()
    crud.getCurrentUser(db, userId=userId)
    plan_specs = default_ddl_plans(normalized_end) if plans is None else plans
    normalized = _normalize_plan_specs(clean_title, plan_specs)

    now = nowIso()
    ddl_id = newId()
    base = EvtBase(
        evtId=ddl_id,
        userId=userId,
        title=clean_title,
        desc=desc,
        evtType="ddl",
        prio=prio,
        stat="todo",
        createdAt=now,
        updatedAt=now,
    )
    db.add(base)
    db.flush()
    db.add(DdlEvt(evtId=ddl_id, endTime=normalized_end, hardDdl=hardDdl))
    db.add(
        ActLog(
            userId=userId,
            actorKind=_actor_kind(src),
            actorId=src,
            action="create",
            targetKind="ddlEvt",
            targetId=ddl_id,
            result="ok",
        )
    )
    db.flush()

    for spec in normalized:
        _add_plan(db, ddl_id=ddl_id, ddl_base=base, spec=spec, src=src)
    for spec in _normalize_reminder_specs(clean_title, ddlReminders or []):
        _add_ddl_reminder(db, ddl_id=ddl_id, ddl_base=base, spec=spec, src=src)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return get_event(db, ddl_id)
