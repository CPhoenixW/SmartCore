from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.server.new_core.models import (
    ComputerMonitorStatus,
    ComputerWorkBlock,
    EvtBase,
    LifeDevice,
    PlanEvt,
)
from app.server.new_core.notify import routeNotify


def _aware(value: str | datetime) -> datetime:
    parsed = (
        value
        if isinstance(value, datetime)
        else datetime.fromisoformat(value.replace("Z", "+00:00"))
    )
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _current_plan(
    db: Session, *, user_id: str, now: datetime
) -> tuple[EvtBase, datetime] | None:
    matches: list[tuple[EvtBase, datetime]] = []
    for base, plan in db.execute(
        select(EvtBase, PlanEvt)
        .join(PlanEvt, PlanEvt.evtId == EvtBase.evtId)
        .where(
            EvtBase.userId == user_id,
            EvtBase.evtType == "plan",
            EvtBase.stat == "todo",
        )
    ).all():
        try:
            start = _aware(plan.stTime).astimezone(UTC)
        except (TypeError, ValueError):
            continue
        end = start + timedelta(minutes=max(1, int(plan.durationMin)))
        if start <= now < end:
            matches.append((base, start))
    return min(matches, key=lambda item: (item[1], item[0].evtId)) if matches else None


def _open_block(db: Session, *, device: LifeDevice) -> ComputerWorkBlock | None:
    return db.scalar(
        select(ComputerWorkBlock)
        .where(
            ComputerWorkBlock.userId == device.userId,
            ComputerWorkBlock.deviceId == device.deviceId,
            ComputerWorkBlock.status == "open",
        )
        .order_by(ComputerWorkBlock.startAt.desc())
    )


def _dedup_key(device_id: str, state_since: str) -> str:
    fingerprint = hashlib.sha256(state_since.encode("utf-8")).hexdigest()[:24]
    return f"computer-attention:{device_id}:{fingerprint}"


def dispatch_attention_reminders(
    db: Session,
    *,
    now: datetime,
    screen_online: Callable[[str], bool],
    idle_minutes: int = 5,
    implicit_focus_active_minutes: int = 20,
) -> int:
    current = _aware(now).astimezone(UTC)
    idle_threshold = timedelta(minutes=max(1, idle_minutes))
    implicit_active_seconds = max(1, implicit_focus_active_minutes) * 60
    sent = 0
    devices = db.scalars(
        select(LifeDevice).where(
            LifeDevice.deviceKind == "computer",
            LifeDevice.stat == "active",
        )
    )
    for device in devices:
        status = db.get(ComputerMonitorStatus, device.deviceId)
        if (
            status is None
            or status.currentState != "idle"
            or status.paused
            or not status.stateSince
            or current - _aware(status.lastHeartbeatAt).astimezone(UTC) > timedelta(seconds=120)
        ):
            continue
        try:
            idle_since = _aware(status.stateSince).astimezone(UTC)
        except (TypeError, ValueError):
            continue

        plan_match = _current_plan(db, user_id=device.userId, now=current)
        if plan_match is not None:
            plan, plan_start = plan_match
            effective_idle_start = max(idle_since, plan_start)
            if current - effective_idle_start < idle_threshold:
                continue
            title = "计划注意力提醒"
            content = f"「{plan.title}」已经暂停操作 {idle_minutes} 分钟，是否继续？"
        else:
            block = _open_block(db, device=device)
            if block is None or int(block.activeSeconds or 0) < implicit_active_seconds:
                continue
            if current - idle_since < idle_threshold:
                continue
            title = "工作注意力提醒"
            content = f"刚才的工作已经暂停 {idle_minutes} 分钟，要继续吗？"

        result = routeNotify(
            db,
            title=title,
            content=content,
            screenOnline=screen_online(device.userId),
            dedupKey=_dedup_key(device.deviceId, status.stateSince),
            evtId=None,
            phase="start",
            userId=device.userId,
        )
        sent += result["stat"] == "sent"
    return sent
