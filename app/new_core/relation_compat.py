from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.new_core import crud
from app.new_core.course_semester import (
    create_course_event,
    list_course_events,
    update_course_event,
)
from app.new_core.custom_reminders import replace_extra_reminders, sync_extra_reminders
from app.new_core.event_relations import (
    apply_reminder_action,
    cancel_event,
    create_plan_event,
    get_event,
    list_events,
    update_event,
)
from app.new_core.models import EvtBase

_installed = False


def install_relation_compat() -> None:
    """Keep older call sites relation-aware while APIs migrate incrementally."""
    global _installed
    if _installed:
        return

    def create_plan(db: Session, **kwargs: Any) -> dict[str, Any]:
        extra_reminders = kwargs.pop("extraReminders", kwargs.pop("reminders", []))
        result = create_plan_event(db, **kwargs, commit=False)
        replace_extra_reminders(
            db,
            result["evtId"],
            extra_reminders,
            commit=False,
        )
        db.commit()
        return get_event(db, result["evtId"])

    def create_course(db: Session, **kwargs: Any) -> dict[str, Any]:
        return create_course_event(db, **kwargs)

    def update(db: Session, evtId: str, **fields: Any) -> dict[str, Any]:
        src = str(fields.pop("src", "api"))
        base = db.get(EvtBase, evtId)
        if base is not None and base.evtType == "course":
            return update_course_event(db, evtId, src=src, **fields)
        extra_reminders = fields.pop("extraReminders", fields.pop("reminders", None))
        result = update_event(db, evtId, src=src, **fields)
        if base is not None and base.evtType == "plan":
            if extra_reminders is None:
                sync_extra_reminders(db, evtId)
            else:
                replace_extra_reminders(db, evtId, extra_reminders)
            result = get_event(db, evtId)
        return result

    def cancel(db: Session, evtId: str, *, src: str = "api") -> dict[str, Any]:
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
        result = apply_reminder_action(
            db,
            evt_id=evtId,
            action=action,
            now=now,
            src=src,
        )
        target_id = result.get("evtId")
        if action == "snooze10" and target_id:
            sync_extra_reminders(db, str(target_id))
            result = get_event(db, str(target_id))
        return result

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
