from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.new_core import crud
from app.new_core.models import ActLog, DdlEvt, DdlPlan, EvtBase, PlanEvt, newId, nowIso

_DEFAULT_TZ = ZoneInfo("Asia/Shanghai")
_ALLOWED_PLAN_ROLES = {"one_day_before", "one_hour_before", "manual"}


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_DEFAULT_TZ)
    return parsed


def _default_plans(end_time: str) -> list[dict[str, Any]]:
    end_dt = _parse_datetime(end_time)
    return [
        {
            "planRole": "one_day_before",
            "stTime": (end_dt - timedelta(days=1)).isoformat(),
            "durationMin": 30,
        },
        {
            "planRole": "one_hour_before",
            "stTime": (end_dt - timedelta(hours=1)).isoformat(),
            "durationMin": 30,
        },
    ]


def _plan_title(ddl_title: str, role: str) -> str:
    labels = {
        "one_day_before": "提前一天",
        "one_hour_before": "提前一小时",
        "manual": "关联计划",
    }
    return f"{ddl_title} · {labels.get(role, '关联计划')}"


def create_ddl_event(
    db: Session,
    *,
    title: str,
    endTime: str,
    hardDdl: bool = False,
    desc: str | None = None,
    prio: str = "high",
    plans: list[dict[str, Any]] | None = None,
    userId: str = crud.DEFAULT_USER_ID,
    src: str = "api",
) -> dict[str, Any]:
    title = title.strip()
    if not title:
        raise ValueError("title required")
    _parse_datetime(endTime)
    crud.getCurrentUser(db, userId=userId)

    plan_specs = _default_plans(endTime) if plans is None else plans
    normalized: list[dict[str, Any]] = []
    seen_roles: set[str] = set()
    for order, raw in enumerate(plan_specs):
        if raw.get("enabled", True) is False:
            continue
        role = str(raw.get("planRole") or raw.get("role") or "manual")
        if role not in _ALLOWED_PLAN_ROLES:
            raise ValueError(f"unsupported planRole: {role}")
        if role in seen_roles:
            raise ValueError(f"duplicate planRole: {role}")
        seen_roles.add(role)
        st_time = str(raw.get("stTime") or "").strip()
        if not st_time:
            raise ValueError(f"stTime required for {role}")
        _parse_datetime(st_time)
        duration = int(raw.get("durationMin") or 30)
        if duration <= 0:
            raise ValueError("durationMin must be greater than 0")
        normalized.append(
            {
                "planRole": role,
                "stTime": st_time,
                "durationMin": duration,
                "title": str(raw.get("title") or _plan_title(title, role)).strip(),
                "sortOrder": int(raw.get("sortOrder", order)),
            }
        )

    now = nowIso()
    ddl_id = newId()
    base = EvtBase(
        evtId=ddl_id,
        userId=userId,
        title=title,
        desc=desc,
        evtType="ddl",
        prio=prio,
        stat="todo",
        createdAt=now,
        updatedAt=now,
    )
    db.add(base)
    db.add(DdlEvt(evtId=ddl_id, endTime=endTime, hardDdl=hardDdl))
    db.add(
        ActLog(
            userId=userId,
            actorKind="user" if src == "api" else "llm",
            actorId=src,
            action="create",
            targetKind="ddlEvt",
            targetId=ddl_id,
            result="ok",
        )
    )

    for spec in normalized:
        plan_id = newId()
        plan_base = EvtBase(
            evtId=plan_id,
            userId=userId,
            title=spec["title"],
            desc="DDL 关联计划",
            evtType="plan",
            prio=prio,
            stat="todo",
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
        db.add(
            DdlPlan(
                ddlEvtId=ddl_id,
                planEvtId=plan_id,
                planRole=spec["planRole"],
                sortOrder=spec["sortOrder"],
            )
        )
        db.add(
            ActLog(
                userId=userId,
                actorKind="system",
                actorId="ddl-plan",
                action="auto_create",
                targetKind="planEvt",
                targetId=plan_id,
                result="ok",
            )
        )

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return next(item for item in crud.listDdlEvt(db) if item["evtId"] == ddl_id)
