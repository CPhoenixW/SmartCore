from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agent.routes import _done, _failed, requireAgentToken
from app.agent.v2_routes import _normalize_query_body
from app.db.session import get_db
from app.new_core.event_relations import query_events


def createRelationQueryRouter() -> APIRouter:
    router = APIRouter(prefix="/agent", tags=["agent-relations"])
    protected = [Depends(requireAgentToken)]

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
