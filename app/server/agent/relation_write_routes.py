from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.server.agent.routes import _done, _failed, requireAgentToken
from app.server.agent.scope import AgentScope, require_agent_scope
from app.server.agent.v2_routes import (
    _normalize_update_patch,
    _resolved_absolute_iso,
    _resolved_iso,
)
from app.server.db.session import get_db
from app.server.new_core.course_semester import create_course_event, update_course_event
from app.server.new_core.ddl_service import (
    create_ddl_event,
    replace_ddl_plans,
    replace_ddl_reminders,
)
from app.server.new_core.event_relations import (
    cancel_event,
    create_plan_event,
    update_commute_plan,
    update_event,
)
from app.server.new_core.models import EvtBase
from app.server.new_core.reminder_service import create_reminder_event, update_reminder_event


def _normalized_plans(body: dict[str, Any]) -> list[dict[str, Any]] | None:
    plans = body.get("plans") or body.get("linkedPlans")
    if plans is None:
        return None
    if not isinstance(plans, list):
        raise ValueError("plans must be an array")
    result: list[dict[str, Any]] = []
    for index, plan in enumerate(plans):
        if not isinstance(plan, dict):
            raise ValueError(f"plans[{index}] must be an object")
        normalized = dict(plan)
        if normalized.get("sortOrder") is None:
            normalized["sortOrder"] = index
        if plan.get("stTime") not in (None, ""):
            normalized["stTime"] = _resolved_iso(
                plan["stTime"],
                body,
                f"plans[{index}].stTime",
            )
        result.append(normalized)
    return result


def _normalized_ddl_reminders(body: dict[str, Any]) -> list[dict[str, Any]] | None:
    reminders = body["ddlReminders"] if "ddlReminders" in body else body.get("linkedReminders")
    if reminders is None:
        return None
    if not isinstance(reminders, list):
        raise ValueError("ddlReminders must be an array")
    result: list[dict[str, Any]] = []
    for index, reminder in enumerate(reminders):
        if not isinstance(reminder, dict):
            raise ValueError(f"ddlReminders[{index}] must be an object")
        normalized = dict(reminder)
        raw_time = reminder.get("triggerTime") or reminder.get("at")
        if raw_time not in (None, ""):
            normalized["triggerTime"] = _resolved_iso(raw_time, body, f"ddlReminders[{index}].triggerTime")
        result.append(normalized)
    return result


def createRelationWriteRouter() -> APIRouter:
    router = APIRouter(prefix="/agent", tags=["agent-relation-writes"])
    protected = [Depends(requireAgentToken), Depends(require_agent_scope)]

    def create(body: dict[str, Any], db: Session, scope: AgentScope) -> dict[str, Any]:
        try:
            evt_type = str(body.get("evtType") or body.get("type") or "").lower()
            if evt_type == "life":
                evt_type = "plan"
            if evt_type in {"reminder", "提醒"}:
                evt_type = "remind"
            title = str(body.get("title") or body.get("courseName") or "").strip()
            if not title:
                raise ValueError("title required")

            if evt_type == "plan":
                raw_time = body.get("stTime") or body.get("dueAt") or body.get("at")
                if raw_time in (None, ""):
                    raise ValueError("stTime required")
                return _done(
                    create_plan_event(
                        db,
                        title=title,
                        stTime=_resolved_iso(raw_time, body, "stTime"),
                        durationMin=int(body.get("durationMin") or 30),
                        desc=body.get("desc") or body.get("description"),
                        prio=body.get("prio") or body.get("priority") or "mid",
                        userId=scope.userId,
                        src="openclaw",
                    )
                )

            if evt_type == "remind":
                raw_time = body.get("triggerTime") or body.get("remindAt") or body.get("at")
                if raw_time in (None, ""):
                    raise ValueError("triggerTime required")
                return _done(
                    create_reminder_event(
                        db,
                        title=title,
                        triggerTime=_resolved_iso(raw_time, body, "triggerTime"),
                        desc=body.get("desc") or body.get("description"),
                        prio=body.get("prio") or body.get("priority") or "mid",
                        userId=scope.userId,
                        src="openclaw",
                    )
                )

            if evt_type == "ddl":
                raw_time = body.get("endTime") or body.get("ddlAt") or body.get("at")
                if raw_time in (None, ""):
                    raise ValueError("endTime required")
                return _done(
                    create_ddl_event(
                        db,
                        title=title,
                        endTime=_resolved_iso(raw_time, body, "endTime"),
                        hardDdl=bool(body.get("hardDdl", False)),
                        desc=body.get("desc") or body.get("description"),
                        prio=body.get("prio") or body.get("priority") or "high",
                        plans=_normalized_plans(body),
                        ddlReminders=_normalized_ddl_reminders(body),
                        userId=scope.userId,
                        src="openclaw",
                    )
                )

            if evt_type == "course":
                semester_start = body.get("semesterStart") or body.get("stDate") or body.get("startDate")
                required = {
                    "courseName": body.get("courseName"),
                    "semesterStart": semester_start,
                    "weekDay": body.get("weekDay") or body.get("weekday"),
                    "stTime": body.get("stTime") or body.get("startTime"),
                    "endTime": body.get("endTime") or body.get("finishTime"),
                }
                missing = [key for key, value in required.items() if value in (None, "")]
                if missing:
                    raise ValueError(f"required fields missing: {', '.join(missing)}")
                return _done(
                    create_course_event(
                        db,
                        title=title,
                        courseName=str(required["courseName"]),
                        teacher=body.get("teacher"),
                        location=body.get("location") or body.get("room"),
                        semesterStart=str(required["semesterStart"]),
                        weekDay=required["weekDay"],
                        stTime=str(required["stTime"]),
                        endTime=str(required["endTime"]),
                        startWeek=int(body.get("startWeek") or 1),
                        endWeek=int(body.get("endWeek") or 16),
                        weekMode=str(body.get("weekMode") or "all"),
                        desc=body.get("desc") or body.get("description"),
                        prio=body.get("prio") or body.get("priority") or "mid",
                        userId=scope.userId,
                        src="openclaw",
                    )
                )
            raise ValueError("unsupported evtType")
        except (ValueError, TypeError, IntegrityError) as exc:
            db.rollback()
            return _failed([str(exc)])

    def update(body: dict[str, Any], db: Session, scope: AgentScope) -> dict[str, Any]:
        evt_id = body.get("evtId") or body.get("eventId")
        if not evt_id:
            return _failed(["evtId required"])
        try:
            base = db.get(EvtBase, str(evt_id))
            if base is None or base.userId != scope.userId:
                raise ValueError(f"evt not found: {evt_id}")
            patch = _normalize_update_patch(body, evt_type=base.evtType)
            if "semesterStart" in body:
                patch["semesterStart"] = body["semesterStart"]
            if base.evtType == "remind":
                raw_time = body.get("triggerTime") or body.get("remindAt")
                if raw_time not in (None, ""):
                    patch["triggerTime"] = _resolved_iso(raw_time, body, "triggerTime")
                if not patch:
                    raise ValueError("no supported update fields")
                return _done(update_reminder_event(db, str(evt_id), src="openclaw", **patch))
            if base.evtType == "course":
                if not patch:
                    raise ValueError("no supported update fields")
                return _done(update_course_event(db, str(evt_id), src="openclaw", **patch))

            plans = _normalized_plans(body) if ("plans" in body or "linkedPlans" in body) else None
            reminders = _normalized_ddl_reminders(body) if ("ddlReminders" in body or "linkedReminders" in body) else None
            if not patch and plans is None and reminders is None:
                raise ValueError("no supported update fields")
            result = update_event(db, str(evt_id), src="openclaw", **patch)
            if base.evtType == "ddl" and plans is not None:
                result = replace_ddl_plans(db, str(evt_id), plans, src="openclaw")
            if base.evtType == "ddl" and reminders is not None:
                result = replace_ddl_reminders(db, str(evt_id), reminders, src="openclaw")
            return _done(result)
        except (ValueError, TypeError, IntegrityError) as exc:
            db.rollback()
            return _failed([str(exc)])

    def update_commute(
        body: dict[str, Any],
        db: Session,
        scope: AgentScope,
    ) -> dict[str, Any]:
        required = ("planEvtId", "reminderEvtId", "departureAt", "commuteMinutes", "endAt")
        missing = [key for key in required if body.get(key) in (None, "")]
        if missing:
            return _failed([f"required fields missing: {', '.join(missing)}"])
        try:
            raw_minutes = body["commuteMinutes"]
            if isinstance(raw_minutes, bool):
                raise ValueError("commuteMinutes must be an integer")
            minutes = int(raw_minutes)
            if isinstance(raw_minutes, float) and raw_minutes != minutes:
                raise ValueError("commuteMinutes must be an integer")
            return _done(
                update_commute_plan(
                    db,
                    plan_evt_id=str(body["planEvtId"]),
                    reminder_evt_id=str(body["reminderEvtId"]),
                    departure_at=_resolved_absolute_iso(
                        body["departureAt"], body, "departureAt"
                    ),
                    commute_minutes=minutes,
                    end_at=_resolved_absolute_iso(body["endAt"], body, "endAt"),
                    user_id=scope.userId,
                    src="openclaw",
                )
            )
        except (ValueError, TypeError, IntegrityError) as exc:
            db.rollback()
            return _failed([str(exc)])

    def delete(body: dict[str, Any], db: Session, scope: AgentScope) -> dict[str, Any]:
        evt_id = body.get("evtId") or body.get("eventId")
        if not evt_id:
            return _failed(["evtId required"])
        try:
            base = db.get(EvtBase, str(evt_id))
            if base is None or base.userId != scope.userId:
                raise ValueError(f"evt not found: {evt_id}")
            return _done(cancel_event(db, str(evt_id), src="openclaw"))
        except (ValueError, TypeError, IntegrityError) as exc:
            db.rollback()
            return _failed([str(exc)])

    @router.post("/db/create_event", dependencies=protected)
    def create_modern(body: dict[str, Any], db: Session = Depends(get_db), scope: AgentScope = Depends(require_agent_scope)) -> dict[str, Any]:
        return create(body, db, scope)

    @router.post("/db/update_event", dependencies=protected)
    def update_modern(body: dict[str, Any], db: Session = Depends(get_db), scope: AgentScope = Depends(require_agent_scope)) -> dict[str, Any]:
        return update(body, db, scope)

    @router.post("/db/update_commute_plan", dependencies=protected)
    def update_commute_modern(
        body: dict[str, Any],
        db: Session = Depends(get_db),
        scope: AgentScope = Depends(require_agent_scope),
    ) -> dict[str, Any]:
        return update_commute(body, db, scope)

    @router.post("/db/delete_event", dependencies=protected)
    def delete_modern(
        body: dict[str, Any],
        db: Session = Depends(get_db),
        scope: AgentScope = Depends(require_agent_scope),
    ) -> dict[str, Any]:
        return delete(body, db, scope)

    return router
