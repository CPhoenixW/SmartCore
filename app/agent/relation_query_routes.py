from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agent.routes import _done, _failed, requireAgentToken
from app.agent.v2_routes import _enhanced_tools, _normalize_query_body
from app.db.session import get_db
from app.new_core.event_relations import query_events


def _relation_tools() -> list[dict[str, Any]]:
    tools = _enhanced_tools()
    for tool in tools:
        if tool.get("name") != "evtQuery":
            continue
        properties = (tool.get("inputSchema") or {}).get("properties") or {}
        linked = properties.get("includeLinkedPlans")
        if isinstance(linked, dict):
            linked["default"] = True
            linked["description"] = "Include DDL-linked and course-generated plan occurrences. Defaults to true."
        evt_type = properties.get("evtType")
        if isinstance(evt_type, dict):
            for variant in evt_type.get("oneOf") or []:
                if not isinstance(variant, dict):
                    continue
                if isinstance(variant.get("enum"), list) and "remind" not in variant["enum"]:
                    variant["enum"].append("remind")
                items = variant.get("items")
                if isinstance(items, dict) and isinstance(items.get("enum"), list) and "remind" not in items["enum"]:
                    items["enum"].append("remind")
    return tools


def createRelationQueryRouter() -> APIRouter:
    router = APIRouter(prefix="/agent", tags=["agent-relations"])
    protected = [Depends(requireAgentToken)]

    @router.get("/tools", dependencies=protected)
    def tools() -> dict[str, Any]:
        now = datetime.now(ZoneInfo("Asia/Shanghai")).replace(microsecond=0)
        definitions = _relation_tools()
        return {
            "ok": True,
            "stat": "done",
            "data": {
                "version": "2026-07-09-course-reminder-v4",
                "authHeader": "X-SmartCore-Agent-Token",
                "requestContext": {
                    "timezone": "Asia/Shanghai",
                    "now": now.isoformat(),
                },
                "relationPolicy": {
                    "course": "Creating or updating a course expands the recurrence into plan occurrences.",
                    "plan": "Every plan automatically owns two reminder events: start minus 10 minutes and end minus 10 minutes.",
                    "reminder": "Reminder events are push-only and hidden unless includeReminders is true.",
                    "weekday": "Monday=1 through Sunday=7; Chinese and English weekday names are accepted.",
                },
                "tools": definitions,
            },
            "errors": [],
            "tools": definitions,
        }

    def execute(body: dict[str, Any] | None, db: Session) -> dict[str, Any]:
        try:
            normalized = _normalize_query_body(body or {})
            normalized.setdefault("includeLinkedPlans", True)
            return _done(query_events(db, normalized))
        except (ValueError, TypeError) as exc:
            return _failed([str(exc)])

    @router.post("/db/query_events", dependencies=protected)
    def query_modern(
        body: dict[str, Any] | None = None,
        db: Session = Depends(get_db),
    ) -> dict[str, Any]:
        return execute(body, db)

    @router.post("/evtQuery", dependencies=protected)
    def query_legacy(
        body: dict[str, Any] | None = None,
        db: Session = Depends(get_db),
    ) -> dict[str, Any]:
        return execute(body, db)

    return router
