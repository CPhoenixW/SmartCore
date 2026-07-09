from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agent.routes import _done, _failed, requireAgentToken
from app.agent.v2_routes import _normalize_update_patch, _resolved_iso
from app.db.session import get_db
from app.new_core.course_semester import create_course_event, update_course_event
from app.new_core.ddl_service import create_ddl_event
from app.new_core.event_relations import create_plan_event, update_event
from app.new_core.models import EvtBase


def createRelationWriteRouter() -> APIRouter:
    router = APIRouter(prefix="/agent", tags=["agent-relation-writes"])
    protected = [Depends(requireAgentToken)]

    def create(body: dict[str, Any], db: Session) -> dict[str, Any]:
        try:
            evt_type = str(body.get("evtType") or body.get("type") or "").lower()
            if evt_type == "life":
                evt_type = "plan"
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
                        src="openclaw",
                    )
                )

            if evt_type == "ddl":
                raw_time = body.get("endTime") or body.get("ddlAt") or body.get("at")
                if raw_time in (None, ""):
                    raise ValueError("endTime required")
                plans = body.get("plans")
                normalized_plans: list[dict[str, Any]] | None = None
                if isinstance(plans, list):
                    normalized_plans = []
                    for index, plan in enumerate(plans):
                        if not isinstance(plan, dict):
                            raise ValueError(f"plans[{index}] must be an object")
                        normalized = dict(plan)
                        if normalized.get("sortOrder") is None:
                            normalized.pop("sortOrder", None)
                        if plan.get("stTime") not in (None, ""):
                            normalized["stTime"] = _resolved_iso(
                                plan["stTime"],
                                body,
                                f"plans[{index}].stTime",
                            )
                        normalized_plans.append(normalized)
                return _done(
                    create_ddl_event(
                        db,
                        title=title,
                        endTime=_resolved_iso(raw_time, body, "endTime"),
                        hardDdl=bool(body.get("hardDdl", False)),
                        desc=body.get("desc") or body.get("description"),
                        prio=body.get("prio") or body.get("priority") or "high",
                        plans=normalized_plans,
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
                        src="openclaw",
                    )
                )
            raise ValueError("unsupported evtType")
        except (ValueError, TypeError, IntegrityError) as exc:
            db.rollback()
            return _failed([str(exc)])

    def update(body: dict[str, Any], db: Session) -> dict[str, Any]:
        evt_id = body.get("evtId") or body.get("eventId")
        if not evt_id:
            return _failed(["evtId required"])
        try:
            base = db.get(EvtBase, str(evt_id))
            if base is None:
                raise ValueError(f"evt not found: {evt_id}")
            patch = _normalize_update_patch(body, evt_type=base.evtType)
            if "semesterStart" in body:
                patch["semesterStart"] = body["semesterStart"]
            if not patch:
                raise ValueError("no supported update fields")
            result = (
                update_course_event(db, str(evt_id), src="openclaw", **patch)
                if base.evtType == "course"
                else update_event(db, str(evt_id), src="openclaw", **patch)
            )
            return _done(result)
        except (ValueError, TypeError, IntegrityError) as exc:
            db.rollback()
            return _failed([str(exc)])

    @router.post("/db/create_event", dependencies=protected)
    def create_modern(body: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
        return create(body, db)

    @router.post("/evtCreate", dependencies=protected)
    def create_legacy(body: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
        return create(body, db)

    @router.post("/db/update_event", dependencies=protected)
    def update_modern(body: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
        return update(body, db)

    @router.post("/evtUpdate", dependencies=protected)
    def update_legacy(body: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
        return update(body, db)

    return router
