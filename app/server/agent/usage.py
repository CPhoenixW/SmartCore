from __future__ import annotations

import logging

from fastapi import Request
from fastapi.routing import APIRoute
from sqlalchemy import text

from app.server.agent.assembly import LEGACY_AGENT_PATHS
from app.server.db.session import SessionLocal
from app.server.new_core.models import newId, nowIso

logger = logging.getLogger(__name__)


def record_agent_route_usage(request: Request, status_code: int) -> None:
    route = request.scope.get("route")
    # Ignore unmatched/random paths so unauthenticated probes cannot create an
    # unbounded number of usage rows. The matched route template is the stable
    # operation identity.
    if not isinstance(route, APIRoute):
        return
    path = route.path
    if not path.startswith("/agent/") and path != "/agent":
        return
    endpoint_callable = getattr(route, "endpoint", None)
    endpoint = (
        f"{endpoint_callable.__module__}.{endpoint_callable.__qualname__}"
        if endpoint_callable is not None
        else "unmatched"
    )
    now = nowIso()
    success = int(status_code < 400)
    client_error = int(400 <= status_code < 500)
    server_error = int(status_code >= 500)
    db = SessionLocal()
    try:
        db.execute(
            text(
                """
                INSERT INTO agentRouteUsage (
                    usageId, method, path, endpoint, compatibility, callCount,
                    successCount, clientErrorCount, serverErrorCount,
                    firstCalledAt, lastCalledAt, lastStatusCode
                ) VALUES (
                    :usage_id, :method, :path, :endpoint, :compatibility, 1,
                    :success, :client_error, :server_error, :now, :now, :status
                )
                ON CONFLICT(method, path, endpoint) DO UPDATE SET
                    compatibility = excluded.compatibility,
                    callCount = agentRouteUsage.callCount + 1,
                    successCount = agentRouteUsage.successCount + excluded.successCount,
                    clientErrorCount = agentRouteUsage.clientErrorCount + excluded.clientErrorCount,
                    serverErrorCount = agentRouteUsage.serverErrorCount + excluded.serverErrorCount,
                    lastCalledAt = excluded.lastCalledAt,
                    lastStatusCode = excluded.lastStatusCode
                """
            ),
            {
                "usage_id": newId(),
                "method": request.method.upper(),
                "path": path,
                "endpoint": endpoint[:300],
                "compatibility": path in LEGACY_AGENT_PATHS,
                "success": success,
                "client_error": client_error,
                "server_error": server_error,
                "now": now,
                "status": status_code,
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        # Observability must never make an Agent operation fail.
        logger.exception("failed to persist Agent route usage")
    finally:
        db.close()
