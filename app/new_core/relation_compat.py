from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.new_core import crud
from app.new_core.course_semester import (
    create_course_event,
    list_course_events,
    update_course_event,
)
from app.new_core.event_relations import (
    apply_reminder_action,
    cancel_event,
    create_plan_event,
    list_events,
    update_event,
)
from app.new_core.models import EvtBase, RemindEvt
from app.new_core.reminder_service import update_reminder_event

_DEFAULT_TZ = ZoneInfo("Asia/Shanghai")
_installed = False


def _parse_now(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_DEFAULT_TZ)
    return parsed.astimezone(_DEFAULT_TZ)


def install_relation_compat() -> None:
    """Keep older call sites relation-aware while APIs migrate incrementally."""
    global _installed
    if _installed:
        return

    def create_plan(db: Session, **kwargs: Any) -> dict[str, Any]:
        kwargs.pop("extraReminders", None)
        kwargs.pop("reminders", None)
        return create_plan_event(db, **kwargs)

    def create_course(db: Session, **kwargs: Any) -> dict[str, Any]:
        return create_course_event(db, **kwargs)

    def update(db: Session, evtId: str, **fields: Any) -> dict[str, Any]:
        src = str(fields.pop("src", "api"))
        base = db.get(EvtBase, evtId)
        if base is not None and base.evtType == "course":
            return update_course_event(db, evtId, src=src, **fields)
        if base is not None and base.evtType == "remind":
            return update_reminder_event(db, evtId, src=src, **fields)
        return update_event(db, evtId, src=src, **fields)

    def cancel(db: Session, evtId: str, *, src: str = "api") -> dict[str, Any]:
        base = db.get(EvtBase, evtId)
        if base is not None and base.evtType == "remind":
            return update_reminder_event(db, evtId, src=src, stat="cancelled")
        return cancel_event(db, evtId, src=src)

    def list_all(db: Session, *, userId: str = crud.DEFAULT_USER_ID) -> list[dict[str, Any]]:
        return list_events(db, user_id=userId)

    def list_plans(db: Session) -> list[dict[str, Any]]:
        return list_events(db, evt_types=["plan"], include_course_templates=False)

    def list_ddls(db: Session) -> list[dict[str, Any]]:
        return list_events(db, evt_types=["ddl"], include_course_templates=False)

    def list_courses(db: Session) -> list[dict[str, Any]]:
        return list_course_events(db)

    def reminder_action(
        db: Session,
        *,
        evtId: str,
        action: str,
        now: str,
        src: str,
    ) -> dict[str, Any]:
        reminder = db.get(RemindEvt, evtId)
        if reminder is not None and reminder.planEvtId is None:
            if action == "done":
                return update_reminder_event(db, evtId, src=src, stat="done")
            if action == "snooze10":
                trigger = _parse_now(now) + timedelta(minutes=10)
                return update_reminder_event(
                    db,
                    evtId,
                    src=src,
                    triggerTime=trigger.isoformat(),
                    stat="todo",
                )
            raise ValueError(f"unknown reminder action: {action}")
        return apply_reminder_action(
            db,
            evt_id=evtId,
            action=action,
            now=now,
            src=src,
        )

    crud.createPlanEvt = create_plan
    crud.createCourseEvt = create_course
    crud.updateEvt = update
    crud.cancelEvt = cancel
    crud.listEvt = list_all
    crud.listPlanEvt = list_plans
    crud.listDdlEvt = list_ddls
    crud.listCourseEvt = list_courses
    crud.applyReminderAction = reminder_action
    _installed = True
