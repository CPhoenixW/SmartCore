from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request
from fastapi.routing import APIRoute
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.server.agent.assembly import LEGACY_AGENT_MIGRATIONS, LEGACY_AGENT_PATHS
from app.server.db.session import SessionLocal
from app.server.new_core.models import (
    AgentRouteObservation,
    AgentRouteUsage,
    newId,
    nowIso,
)

logger = logging.getLogger(__name__)
LEGACY_AGENT_COMPATIBILITY_DAYS = 30
_OBSERVATION_TZ = ZoneInfo("Asia/Shanghai")


def _endpoint_name(route: APIRoute) -> str:
    endpoint_callable = getattr(route, "endpoint", None)
    if endpoint_callable is None:
        return "unmatched"
    return f"{endpoint_callable.__module__}.{endpoint_callable.__qualname__}"[:300]


def sync_agent_route_observations(router: APIRouter) -> None:
    """Seed every assembled operation while preserving its first observation time."""
    now = nowIso()
    db = SessionLocal()
    try:
        db.execute(text("UPDATE agentRouteObservation SET active = 0"))
        for route in router.routes:
            if not isinstance(route, APIRoute):
                continue
            for method in sorted(route.methods or ()):
                db.execute(
                    text(
                        """
                        INSERT INTO agentRouteObservation (
                            method, path, endpoint, compatibility,
                            observedSinceAt, lastAssembledAt, active
                        ) VALUES (
                            :method, :path, :endpoint, :compatibility,
                            :now, :now, 1
                        )
                        ON CONFLICT(method, path) DO UPDATE SET
                            endpoint = excluded.endpoint,
                            compatibility = excluded.compatibility,
                            lastAssembledAt = excluded.lastAssembledAt,
                            active = 1
                        """
                    ),
                    {
                        "method": method,
                        "path": route.path,
                        "endpoint": _endpoint_name(route),
                        "compatibility": route.path in LEGACY_AGENT_PATHS,
                        "now": now,
                    },
                )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_OBSERVATION_TZ)
    return parsed


def legacy_agent_route_readiness(
    db: Session,
    *,
    now: datetime | None = None,
) -> dict[str, object]:
    """Return the auditable quiet-window state for every active legacy path."""
    current = now or datetime.now(_OBSERVATION_TZ)
    observations = list(
        db.scalars(
            select(AgentRouteObservation)
            .where(
                AgentRouteObservation.compatibility.is_(True),
                AgentRouteObservation.active.is_(True),
            )
            .order_by(AgentRouteObservation.path, AgentRouteObservation.method)
        )
    )
    usage_rows = db.execute(
        select(
            AgentRouteUsage.method,
            AgentRouteUsage.path,
            func.sum(AgentRouteUsage.callCount),
            func.sum(AgentRouteUsage.successCount),
            func.sum(AgentRouteUsage.clientErrorCount),
            func.sum(AgentRouteUsage.serverErrorCount),
            func.min(AgentRouteUsage.firstCalledAt),
            func.max(AgentRouteUsage.lastCalledAt),
        ).group_by(AgentRouteUsage.method, AgentRouteUsage.path)
    ).all()
    usage_by_operation = {
        (method, path): {
            "callCount": int(call_count or 0),
            "successCount": int(success_count or 0),
            "clientErrorCount": int(client_error_count or 0),
            "serverErrorCount": int(server_error_count or 0),
            "firstCalledAt": first_called_at,
            "lastCalledAt": last_called_at,
        }
        for (
            method,
            path,
            call_count,
            success_count,
            client_error_count,
            server_error_count,
            first_called_at,
            last_called_at,
        ) in usage_rows
    }
    routes: list[dict[str, object]] = []
    for observation in observations:
        migration = LEGACY_AGENT_MIGRATIONS[observation.path]
        usage = usage_by_operation.get(
            (observation.method, observation.path),
            {
                "callCount": 0,
                "successCount": 0,
                "clientErrorCount": 0,
                "serverErrorCount": 0,
                "firstCalledAt": None,
                "lastCalledAt": None,
            },
        )
        quiet_since_at = str(usage["lastCalledAt"] or observation.observedSinceAt)
        eligible_after = _parse_time(quiet_since_at) + timedelta(
            days=LEGACY_AGENT_COMPATIBILITY_DAYS
        )
        routes.append(
            {
                "method": observation.method,
                "path": observation.path,
                "endpoint": observation.endpoint,
                "replacementPath": migration.replacementPath,
                "retirementWave": migration.retirementWave,
                "observedSinceAt": observation.observedSinceAt,
                "lastAssembledAt": observation.lastAssembledAt,
                **usage,
                "quietSinceAt": quiet_since_at,
                "eligibleAfter": eligible_after.isoformat(),
                "eligibleForRemoval": current >= eligible_after,
            }
        )
    waves = [
        {
            "wave": wave,
            "paths": [
                str(route["path"])
                for route in routes
                if route["retirementWave"] == wave
            ],
            "allEligibleForRemoval": all(
                bool(route["eligibleForRemoval"])
                for route in routes
                if route["retirementWave"] == wave
            ),
        }
        for wave in sorted({int(route["retirementWave"]) for route in routes})
    ]
    return {
        "observationDays": LEGACY_AGENT_COMPATIBILITY_DAYS,
        "generatedAt": current.isoformat(),
        "allEligibleForRemoval": bool(routes)
        and all(bool(route["eligibleForRemoval"]) for route in routes),
        "waves": waves,
        "routes": routes,
    }


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
    endpoint = _endpoint_name(route)
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
                "endpoint": endpoint,
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
