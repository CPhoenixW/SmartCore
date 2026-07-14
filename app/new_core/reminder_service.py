from __future__ import annotations

from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.new_core import crud
from app.new_core.models import ActLog, EvtBase, RemindEvt, newId, nowIso

_DEFAULT_TZ = ZoneInfo("Asia/Shanghai")
_DEFAULT_USER_ID = "default"
_ALLOWED_STATS = {"todo", "done", "cancelled"}
_ALLOWED_PRIORITIES = {"low", "mid", "high"}


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_DEFAULT_TZ)
    return parsed.astimezone(_DEFAULT_TZ).replace(microsecond=0)


def _event_dict(base: EvtBase, remind: RemindEvt) -> dict[str, Any]:
    return {
        "evtId": base.evtId,
        "userId": base.userId,
        "title": base.title,
        "desc": base.desc,
        "evtType": "remind",
        "prio": base.prio,
        "stat": base.stat,
        "createdAt": base.createdAt,
        "updatedAt": base.updatedAt,
        "triggerTime": remind.triggerTime,
        "ddlEvtId": remind.ddlEvtId,
        "remindKind": remind.remindKind,
        "firedAt": remind.firedAt,
        "standalone": remind.planEvtId is None and remind.ddlEvtId is None,
    }


def _ensure_standalone(remind: RemindEvt | None, evt_id: str) -> RemindEvt:
    if remind is None:
        raise ValueError(f"reminder not found: {evt_id}")
    if remind.planEvtId is not None or remind.ddlEvtId is not None:
        raise ValueError("linked reminders cannot be edited directly")
    return remind


def _priority(value: Any) -> str:
    priority = str(value or "mid").strip().lower()
    if priority not in _ALLOWED_PRIORITIES:
        raise ValueError("prio must be low, mid, or high")
    return priority


def _status(value: Any) -> str:
    status = str(value or "todo").strip().lower()
    if status not in _ALLOWED_STATS:
        raise ValueError("stat must be todo, done, or cancelled")
    return status


def _write_action_log(
    db: Session,
    *,
    user_id: str,
    evt_id: str,
    action: str,
    src: str,
) -> None:
    # Use the generic `evt` target kind so existing databases whose actLog
    # CHECK constraint predates standalone reminders can still persist writes.
    db.add(
        ActLog(
            userId=user_id,
            actorKind="llm" if src in {"openclaw", "llm"} else "user",
            actorId=src,
            action=action,
            targetKind="evt",
            targetId=evt_id,
            result="ok",
        )
    )


def create_reminder_event(
    db: Session,
    *,
    title: str,
    triggerTime: str,
    desc: str | None = None,
    prio: str = "mid",
    userId: str = _DEFAULT_USER_ID,
    src: str = "api",
) -> dict[str, Any]:
    clean_title = str(title).strip()
    if not clean_title:
        raise ValueError("title required")
    trigger = _parse_datetime(triggerTime).isoformat()
    crud.getCurrentUser(db, userId=userId)
    now = nowIso()
    evt_id = newId()
    base = EvtBase(
        evtId=evt_id,
        userId=userId,
        title=clean_title,
        desc=desc,
        evtType="remind",
        prio=_priority(prio),
        stat="todo",
        createdAt=now,
        updatedAt=now,
    )
    remind = RemindEvt(
        evtId=evt_id,
        planEvtId=None,
        ddlEvtId=None,
        remindKind="manual",
        triggerTime=trigger,
        offsetMin=0,
        firedAt=None,
    )
    db.add(base)
    db.add(remind)
    _write_action_log(
        db,
        user_id=userId,
        evt_id=evt_id,
        action="create",
        src=src,
    )
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return _event_dict(base, remind)


def get_reminder_event(db: Session, evt_id: str) -> dict[str, Any]:
    base = db.get(EvtBase, evt_id)
    remind = _ensure_standalone(db.get(RemindEvt, evt_id), evt_id)
    if base is None:
        raise ValueError(f"reminder not found: {evt_id}")
    return _event_dict(base, remind)


def update_reminder_event(
    db: Session,
    evt_id: str,
    *,
    src: str = "api",
    **fields: Any,
) -> dict[str, Any]:
    base = db.get(EvtBase, evt_id)
    remind = _ensure_standalone(db.get(RemindEvt, evt_id), evt_id)
    if base is None:
        raise ValueError(f"reminder not found: {evt_id}")

    if "title" in fields and fields["title"] is not None:
        clean_title = str(fields["title"]).strip()
        if not clean_title:
            raise ValueError("title required")
        base.title = clean_title
    if "desc" in fields:
        base.desc = fields["desc"] or None
    if "prio" in fields and fields["prio"] is not None:
        base.prio = _priority(fields["prio"])
    if "stat" in fields and fields["stat"] is not None:
        next_status = _status(fields["stat"])
        base.stat = next_status
        if next_status == "todo":
            remind.firedAt = None

    if "triggerTime" in fields and fields["triggerTime"] is not None:
        normalized = _parse_datetime(str(fields["triggerTime"])).isoformat()
        if remind.triggerTime != normalized:
            remind.triggerTime = normalized
            remind.firedAt = None
            if "stat" not in fields and base.stat == "done":
                base.stat = "todo"

    base.updatedAt = nowIso()
    _write_action_log(
        db,
        user_id=base.userId,
        evt_id=evt_id,
        action="update",
        src=src,
    )
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return _event_dict(base, remind)


def list_reminder_events(
    db: Session,
    *,
    user_id: str = _DEFAULT_USER_ID,
    date_value: str | None = None,
    stats: list[str] | None = None,
    text: str | None = None,
) -> list[dict[str, Any]]:
    rows = db.execute(
        select(EvtBase, RemindEvt)
        .join(RemindEvt, RemindEvt.evtId == EvtBase.evtId)
        .where(EvtBase.userId == user_id, RemindEvt.planEvtId.is_(None))
        .order_by(RemindEvt.triggerTime.asc())
    ).all()
    allowed_stats = {str(item) for item in stats or []}
    query = str(text or "").strip().lower()
    target_date = date.fromisoformat(date_value) if date_value else None
    result: list[dict[str, Any]] = []
    for base, remind in rows:
        if allowed_stats and base.stat not in allowed_stats:
            continue
        item = _event_dict(base, remind)
        if query and query not in f"{base.title} {base.desc or ''} {remind.triggerTime}".lower():
            continue
        if target_date:
            trigger = _parse_datetime(remind.triggerTime)
            start = datetime.combine(target_date, time.min, tzinfo=_DEFAULT_TZ)
            end = datetime.combine(target_date, time.max, tzinfo=_DEFAULT_TZ)
            if not (start <= trigger <= end):
                continue
        result.append(item)
    return result
