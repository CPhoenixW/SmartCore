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
from app.new_core.event_search import filter_events_by_text


def _relation_tools() -> list[dict[str, Any]]:
    tools = _enhanced_tools()
    for tool in tools:
        name = tool.get("name")
        properties = (tool.get("inputSchema") or {}).get("properties") or {}
        if name == "evtQuery":
            linked = properties.get("includeLinkedPlans")
            if isinstance(linked, dict):
                linked["default"] = True
                linked["description"] = "Include DDL-linked and course-generated plan occurrences. Defaults to true."
            text = properties.get("text") or properties.get("keyword")
            if isinstance(text, dict):
                text["description"] = "Search title, description, date, weekday, or clock time such as 2026-09-01, 星期二, or 08:00."
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
        if name in {"evtCreate", "evtUpdate"}:
            properties["semesterStart"] = {
                "type": "string",
                "format": "date",
                "description": "Semester start date. Course occurrences are calculated from this date and week numbers.",
            }
            properties["startWeek"] = {
                "type": "integer",
                "minimum": 1,
                "default": 1,
            }
            properties["endWeek"] = {
                "type": "integer",
                "minimum": 1,
                "default": 16,
            }
            if isinstance(properties.get("stDate"), dict):
                properties["stDate"]["description"] = "Deprecated course alias for semesterStart."
            if isinstance(properties.get("endDate"), dict):
                properties["endDate"]["description"] = "Deprecated for courses; use endWeek."
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
                "version": "2026-07-09-semester-course-v5",
                "authHeader": "X-SmartCore-Agent-Token",
                "requestContext": {
                    "timezone": "Asia/Shanghai",
                    "now": now.isoformat(),
                },
                "relationPolicy": {
                    "course": "A course uses semesterStart plus startWeek/endWeek, weekday, and clock time to create plan occurrences.",
                    "plan": "Every plan automatically owns two reminder events: start minus 10 minutes and end minus 10 minutes.",
                    "reminder": "Reminder events are push-only and hidden unless includeReminders is true.",
                    "weekday": "Monday=1 through Sunday=7; Chinese and English weekday names are accepted.",
                    "search": "Event text search also matches dates, weekdays, and times.",
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
            search_text = normalized.pop("text", None) or normalized.pop("keyword", None)
            result = query_events(db, normalized)
            items = []
            for item in result.get("items", []):
                if item.get("evtType") == "course":
                    item = dict(item)
                    item.setdefault("semesterStart", item.get("stDate"))
                items.append(item)
            filtered = filter_events_by_text(items, search_text)
            limit = max(1, min(500, int(normalized.get("limit") or 100)))
            return _done(
                {
                    "items": filtered[:limit],
                    "count": min(len(filtered), limit),
                    "total": len(filtered),
                }
            )
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
