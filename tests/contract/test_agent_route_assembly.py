from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.routing import APIRoute

from app.server.agent.assembly import (
    LEGACY_AGENT_MIGRATIONS,
    LEGACY_AGENT_PATHS,
    createAssembledAgentRouter,
)
from app.server.agent.usage import (
    LEGACY_AGENT_COMPATIBILITY_DAYS,
    legacy_agent_route_readiness,
)
from app.server.db.session import SessionLocal
from app.server.main import create_app
from app.server.new_core.models import AgentRouteObservation, AgentRouteUsage

pytestmark = pytest.mark.contract

_SNAPSHOT = Path(__file__).parent / "snapshots" / "assembled_agent_routes.json"
_REPOSITORY = Path(__file__).resolve().parents[2]


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
    assert {str(row["path"]) for row in actual if row["deprecated"]} == LEGACY_AGENT_PATHS

    db = SessionLocal()
    try:
        observations = db.query(AgentRouteObservation).filter_by(active=True).all()
        observed_since = {
            (row.method, row.path): row.observedSinceAt for row in observations
        }
        assert {(row.method, row.path) for row in observations} == {
            (str(row["method"]), str(row["path"])) for row in actual
        }
        assert {row.path for row in observations if row.compatibility} == LEGACY_AGENT_PATHS
        assert all(row.observedSinceAt and row.lastAssembledAt for row in observations)
    finally:
        db.close()

    create_app()
    db = SessionLocal()
    try:
        restarted = db.query(AgentRouteObservation).filter_by(active=True).all()
        assert {(row.method, row.path): row.observedSinceAt for row in restarted} == observed_since
    finally:
        db.close()


def test_legacy_migration_manifest_has_live_replacements_and_no_first_party_urls() -> None:
    paths = {route.path for route in createAssembledAgentRouter().routes}
    assert set(LEGACY_AGENT_MIGRATIONS) == LEGACY_AGENT_PATHS
    assert {
        migration.replacementPath
        for migration in LEGACY_AGENT_MIGRATIONS.values()
        if migration.replacementPath is not None
    } <= paths
    assert {migration.retirementWave for migration in LEGACY_AGENT_MIGRATIONS.values()} == {3}

    first_party_files = [
        *(_REPOSITORY / "openclaw").rglob("*.py"),
        *(_REPOSITORY / "openclaw").rglob("*.md"),
        *(_REPOSITORY / "openclaw").rglob("*.json"),
        *(_REPOSITORY / "scripts").rglob("*.py"),
        *(_REPOSITORY / "scripts").rglob("*.sh"),
        *(
            path
            for path in (_REPOSITORY / "app" / "server").rglob("*.py")
            if "agent" not in path.relative_to(_REPOSITORY / "app" / "server").parts
        ),
    ]
    direct_references: list[str] = []
    for path in first_party_files:
        source = path.read_text(encoding="utf-8")
        for legacy_path in LEGACY_AGENT_PATHS:
            if f'"{legacy_path}"' in source or f"'{legacy_path}'" in source:
                direct_references.append(f"{path.relative_to(_REPOSITORY)}:{legacy_path}")
    assert direct_references == []

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


def test_legacy_route_removal_requires_a_complete_quiet_window(client) -> None:
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    old_observation = (now - timedelta(days=LEGACY_AGENT_COMPATIBILITY_DAYS + 1)).isoformat()
    db = SessionLocal()
    try:
        for row in db.query(AgentRouteObservation).filter_by(compatibility=True, active=True):
            row.observedSinceAt = old_observation
        db.commit()
        before = legacy_agent_route_readiness(db, now=now)
        assert before["allEligibleForRemoval"] is True
        assert len(before["routes"]) == len(LEGACY_AGENT_PATHS)
        assert [wave["wave"] for wave in before["waves"]] == [3]
        assert all(wave["allEligibleForRemoval"] is True for wave in before["waves"])
        assert all("retirementWave" in row and "replacementPath" in row for row in before["routes"])
    finally:
        db.close()

    response = client.post("/agent/sendText", json={})
    assert response.status_code == 401

    db = SessionLocal()
    try:
        after = legacy_agent_route_readiness(db, now=now + timedelta(seconds=1))
        send_text_route = next(
            row for row in after["routes"] if row["path"] == "/agent/sendText"
        )
        assert send_text_route["callCount"] == 1
        assert send_text_route["clientErrorCount"] == 1
        assert send_text_route["eligibleForRemoval"] is False
        assert after["allEligibleForRemoval"] is False
        assert after["waves"][0]["allEligibleForRemoval"] is False
    finally:
        db.close()
