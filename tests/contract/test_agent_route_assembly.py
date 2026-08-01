from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest
from fastapi.routing import APIRoute

from app.server.db.session import SessionLocal
from app.server.main import create_app
from app.server.new_core.models import AgentRouteUsage

pytestmark = pytest.mark.contract

_SNAPSHOT = Path(__file__).parent / "snapshots" / "assembled_agent_routes.json"


def _walk_api_routes(routes):
    for route in routes:
        if type(route).__name__ == "_IncludedRouter":
            yield from _walk_api_routes(route.original_router.routes)
        elif isinstance(route, APIRoute):
            yield route


def _agent_route_snapshot() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for route in _walk_api_routes(create_app().routes):
        if not route.path.startswith("/agent"):
            continue
        endpoint = route.endpoint
        endpoint_name = f"{endpoint.__module__}.{endpoint.__qualname__}"
        for method in sorted(route.methods or ()):
            rows.append(
                {
                    "method": method,
                    "path": route.path,
                    "endpoint": endpoint_name,
                    "deprecated": bool(route.deprecated),
                }
            )
    return sorted(rows, key=lambda item: (str(item["path"]), str(item["method"])))


def test_assembled_agent_routes_match_snapshot_and_are_unique(app_env) -> None:
    actual = _agent_route_snapshot()
    expected = json.loads(_SNAPSHOT.read_text(encoding="utf-8"))
    counts = Counter((row["method"], row["path"]) for row in actual)

    assert actual == expected
    assert all(count == 1 for count in counts.values())


def test_agent_route_usage_is_persisted_without_request_payload(client) -> None:
    response = client.get("/agent/tools")
    assert response.status_code == 401

    db = SessionLocal()
    try:
        row = db.query(AgentRouteUsage).filter_by(method="GET", path="/agent/tools").one()
        assert row.callCount == 1
        assert row.clientErrorCount == 1
        assert row.compatibility is False
        assert "tools" in row.endpoint
    finally:
        db.close()


def test_unmatched_agent_paths_do_not_create_usage_dimensions(client) -> None:
    response = client.get("/agent/random-probe-that-is-not-a-route")
    assert response.status_code == 404

    db = SessionLocal()
    try:
        assert db.query(AgentRouteUsage).count() == 0
    finally:
        db.close()
