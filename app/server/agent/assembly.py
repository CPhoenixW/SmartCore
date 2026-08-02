from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import APIRouter
from fastapi.routing import APIRoute

from app.server.agent.daily_summary_routes import createDailySummaryAgentRouter
from app.server.agent.feedback_routes import createFeedbackRouter
from app.server.agent.relation_query_routes import createRelationQueryRouter
from app.server.agent.relation_write_routes import createRelationWriteRouter
from app.server.agent.routes import createAgentRouter
from app.server.agent.v2_routes import createAgentV2Router
from app.server.computer.agent_routes import createComputerAgentRouter


@dataclass(frozen=True)
class _RouterSource:
    name: str
    factory: Callable[[], APIRouter]


@dataclass(frozen=True)
class LegacyAgentMigration:
    replacementPath: str | None
    retirementWave: int


_SOURCES = (
    _RouterSource("relation_query", createRelationQueryRouter),
    _RouterSource("relation_write", createRelationWriteRouter),
    _RouterSource("feedback", createFeedbackRouter),
    _RouterSource("daily_summary", createDailySummaryAgentRouter),
    _RouterSource("computer", createComputerAgentRouter),
    _RouterSource("v2", createAgentV2Router),
    _RouterSource("idea_and_screen", createAgentRouter),
)

LEGACY_AGENT_MIGRATIONS = {
    # Wave 3: external feedback side effects.
    "/agent/sendText": LegacyAgentMigration("/agent/feedback/send_text", 3),
    "/agent/sendCard": LegacyAgentMigration("/agent/feedback/send_card", 3),
    "/agent/screenPush": LegacyAgentMigration("/agent/feedback/screen_push", 3),
}
LEGACY_AGENT_PATHS = frozenset(LEGACY_AGENT_MIGRATIONS)


def _operations(route: APIRoute) -> tuple[tuple[str, str], ...]:
    return tuple((method, route.path) for method in sorted(route.methods or ()))


def createAssembledAgentRouter() -> APIRouter:
    """Build the Agent surface with exactly one handler per method and path."""
    source_routes: list[tuple[str, APIRoute]] = []
    counts: Counter[tuple[str, str]] = Counter()
    for source in _SOURCES:
        for route in source.factory().routes:
            if not isinstance(route, APIRoute):
                continue
            source_routes.append((source.name, route))
            counts.update(_operations(route))

    duplicates = {operation for operation, count in counts.items() if count > 1}
    if duplicates:
        raise RuntimeError(
            f"Agent operations must have exactly one implementation: {sorted(duplicates)}"
        )

    assembled = APIRouter()
    selected: set[tuple[str, str]] = set()
    for _source_name, route in source_routes:
        operations = _operations(route)
        if not operations:
            continue
        for operation in operations:
            if operation in selected:
                raise RuntimeError(f"duplicate Agent operation selected: {operation}")
        route.deprecated = route.path in LEGACY_AGENT_PATHS
        assembled.routes.append(route)
        selected.update(operations)

    return assembled
