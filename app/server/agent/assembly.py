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


_SOURCES = (
    _RouterSource("relation_query", createRelationQueryRouter),
    _RouterSource("relation_write", createRelationWriteRouter),
    _RouterSource("feedback", createFeedbackRouter),
    _RouterSource("daily_summary", createDailySummaryAgentRouter),
    _RouterSource("computer", createComputerAgentRouter),
    _RouterSource("v2", createAgentV2Router),
    _RouterSource("general", createAgentRouter),
)

# Duplicate operations must always name their authoritative implementation here.
# This makes handler ownership reviewable instead of relying on include order.
_OPERATION_OWNERS: dict[tuple[str, str], str] = {
    ("GET", "/agent/tools"): "relation_query",
    ("POST", "/agent/db/query_events"): "relation_query",
    ("POST", "/agent/evtQuery"): "relation_query",
    ("POST", "/agent/db/create_event"): "relation_write",
    ("POST", "/agent/db/update_event"): "relation_write",
    ("POST", "/agent/db/delete_event"): "relation_write",
    ("POST", "/agent/evtCreate"): "relation_write",
    ("POST", "/agent/evtUpdate"): "relation_write",
    ("POST", "/agent/evtDelete"): "relation_write",
    ("POST", "/agent/feedback/send_text"): "feedback",
    ("POST", "/agent/feedback/send_card"): "feedback",
    ("POST", "/agent/feedback/send_query_result_card"): "feedback",
    ("POST", "/agent/feedback/send_operation_success_card"): "feedback",
    ("POST", "/agent/feedback/send_reminder_card"): "feedback",
    ("POST", "/agent/sendText"): "feedback",
    ("POST", "/agent/sendCard"): "feedback",
}

LEGACY_AGENT_PATHS = frozenset(
    {
        "/agent/evtQuery",
        "/agent/evtCreate",
        "/agent/evtUpdate",
        "/agent/evtDelete",
        "/agent/sendText",
        "/agent/sendCard",
        "/agent/ideaCapture",
        "/agent/ideaToEvt",
        "/agent/media/ocr",
        "/agent/screenPush",
    }
)


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

    undeclared_duplicates = {
        operation for operation, count in counts.items()
        if count > 1 and operation not in _OPERATION_OWNERS
    }
    if undeclared_duplicates:
        raise RuntimeError(
            f"Agent operation owners are not declared: {sorted(undeclared_duplicates)}"
        )

    assembled = APIRouter()
    selected: set[tuple[str, str]] = set()
    for source_name, route in source_routes:
        operations = _operations(route)
        if not operations:
            continue
        if any(
            counts[operation] > 1
            and _OPERATION_OWNERS.get(operation) != source_name
            for operation in operations
        ):
            continue
        for operation in operations:
            if operation in selected:
                raise RuntimeError(f"duplicate Agent operation selected: {operation}")
        route.deprecated = route.path in LEGACY_AGENT_PATHS
        assembled.routes.append(route)
        selected.update(operations)

    missing = set(_OPERATION_OWNERS) - selected
    if missing:
        raise RuntimeError(f"declared Agent operations are missing: {sorted(missing)}")
    return assembled
