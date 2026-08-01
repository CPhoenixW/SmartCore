from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.server.agent.assembly import createAssembledAgentRouter
from app.server.db.session import SessionLocal
from app.server.new_core.event_relations import create_plan_event
from app.server.new_core.models import EvtBase
from tests.factories import create_user

pytestmark = pytest.mark.contract


def test_router_exposes_canonical_and_legacy_paths() -> None:
    paths = {route.path for route in createAssembledAgentRouter().routes}
    expected = {
        "/agent/tools",
        "/agent/db/query_events",
        "/agent/evtQuery",
        "/agent/db/create_event",
        "/agent/evtCreate",
        "/agent/db/update_event",
        "/agent/evtUpdate",
        "/agent/db/delete_event",
        "/agent/evtDelete",
        "/agent/idea/capture",
        "/agent/ideaCapture",
        "/agent/idea/to_event",
        "/agent/ideaToEvt",
        "/agent/feedback/send_text",
        "/agent/sendText",
        "/agent/feedback/send_card",
        "/agent/sendCard",
        "/agent/feedback/screen_push",
        "/agent/screenPush",
    }
    assert expected.issubset(paths)


def test_router_sets_and_scoped_legacy_delete_remain_compatible(
    client: TestClient,
    agent_headers,
) -> None:
    paths = {route.path for route in createAssembledAgentRouter().routes}

    assert {
        "/agent/context",
        "/agent/tools",
        "/agent/db/query_events",
        "/agent/db/create_event",
        "/agent/db/update_event",
    }.issubset(paths)
    assert {"/agent/evtQuery", "/agent/evtCreate", "/agent/evtUpdate"}.issubset(paths)

    with SessionLocal() as db:
        create_user(db, user_id="other")
        foreign = create_plan_event(
            db,
            userId="other",
            title="Other user's plan",
            stTime="2026-07-25T09:00:00+08:00",
        )

    response = client.post(
        "/agent/evtDelete",
        headers=agent_headers("default"),
        json={"evtId": foreign["evtId"]},
    )

    assert response.status_code == 200
    assert response.json()["ok"] is False
    with SessionLocal() as db:
        assert db.get(EvtBase, foreign["evtId"]).stat == "todo"
