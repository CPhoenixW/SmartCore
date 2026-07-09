from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agent.routes import _done, _failed, requireAgentToken
from app.agent.v2_routes import _normalize_query_body, _normalize_update_patch, _resolved_iso
from app.db.session import get_db
from app.new_core.ddl_service import create_ddl_event
from app.new_core.event_relations import (
    create_course_event,
    create_plan_event,
    query_events,
    update_event,
)
from app.new_core.models import EvtBase


def createLegacyTimeRouter() -> APIRouter:
    """Keep historical OpenClaw paths consistent with the modern agent contract."""

    router = APIRouter(prefix="/agent", tags=["agent-legacy-time"])
    protected = [Depends(requireAgentToken)]

    @router.post("/evtQuery", dependencies=protected)
    def legacy_query(
        body: dict[str, Any] | None = None,
        db: Session = Depends(get_db),
    ) -> dict[str, Any]:
        try:
            return _done(query_events(db, _normalize_query_body(body or {})))
        except (ValueError, TypeError) as exc:
            return _failed([str(exc)])

    @router.post("/evtCreate", dependencies=protected)
    def legacy_create(
        body: dict[str, Any],
        db: Session = Depends(get_db),
    ) -> dict[str, Any]:
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
                            normalized["stTime"] = _resolved_iso(plan["stTime"], body, f"plans[{index}].stTime")
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
                required = ("courseName", "stTime", "endTime", "stDate", "endDate", "weekDay")
                missing = [key for key in required if body.get(key) in (None, "")]
                if missing:
                    raise ValueError(f"required fields missing: {', '.join(missing)}")
                return _done(
                    create_course_event(
                        db,
                        title=title,
                        courseName=str(body["courseName"]),
                        teacher=body.get("teacher"),
                        location=body.get("location") or body.get("room"),
                        stTime=str(body["stTime"]),
                        endTime=str(body["endTime"]),
                        stDate=str(body["stDate"]),
                        endDate=str(body["endDate"]),
                        weekDay=body["weekDay"],
                        startWeek=int(body["startWeek"]) if body.get("startWeek") is not None else None,
                        endWeek=int(body["endWeek"]) if body.get("endWeek") is not None else None,
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

    @router.post("/evtUpdate", dependencies=protected)
    def legacy_update(
        body: dict[str, Any],
        db: Session = Depends(get_db),
    ) -> dict[str, Any]:
        evt_id = body.get("evtId") or body.get("eventId")
        if not evt_id:
            return _failed(["evtId required"])
        try:
            base = db.get(EvtBase, str(evt_id))
            if base is None:
                raise ValueError(f"evt not found: {evt_id}")
            patch = _normalize_update_patch(body, evt_type=base.evtType)
            if not patch:
                raise ValueError("no supported update fields")
            return _done(update_event(db, str(evt_id), src="openclaw", **patch))
        except (ValueError, TypeError, IntegrityError) as exc:
            db.rollback()
            return _failed([str(exc)])

    return router
