from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from app.agent import routes


@dataclass
class _Link:
    ddlEvtId: str
    planEvtId: str
    planRole: str
    sortOrder: int


class _ScalarRows:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return self._rows


class _FakeDb:
    def __init__(self, links: list[_Link]) -> None:
        self.links = links

    def scalars(self, _statement: Any) -> _ScalarRows:
        return _ScalarRows(self.links)


def test_agent_tools_keep_stable_names_and_aliases() -> None:
    tools = {item["name"]: item for item in routes._AGENT_TOOLS}

    assert tools["evtQuery"]["path"] == "/agent/db/query_events"
    assert "/agent/evtQuery" in tools["evtQuery"]["legacyPaths"]
    assert tools["evtCreate"]["path"] == "/agent/db/create_event"
    assert tools["evtUpdate"]["path"] == "/agent/db/update_event"
    assert tools["evtDelete"]["path"] == "/agent/db/delete_event"
    assert tools["sendFeishuText"]["path"] == "/agent/feedback/send_text"
    assert tools["sendFeishuCard"]["path"] == "/agent/feedback/send_card"


def test_query_events_exposes_ddl_link_for_linked_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    events = [
        {
            "evtId": "ddl-1",
            "evtType": "ddl",
            "title": "提交报告",
            "stat": "todo",
            "endTime": "2026-07-08T20:00:00+08:00",
            "plans": [],
        },
        {
            "evtId": "plan-linked",
            "evtType": "plan",
            "title": "提交报告 · 提前一天",
            "stat": "todo",
            "stTime": "2026-07-07T20:00:00+08:00",
            "durationMin": 30,
        },
        {
            "evtId": "plan-free",
            "evtType": "plan",
            "title": "复习",
            "stat": "todo",
            "stTime": "2026-07-07T21:00:00+08:00",
            "durationMin": 30,
        },
    ]
    monkeypatch.setattr(routes.crud, "listEvt", lambda _db: events)
    db = _FakeDb([_Link("ddl-1", "plan-linked", "one_day_before", 0)])

    result = routes._query_events(
        db,
        {
            "stat": "todo",
            "timeRange": {
                "start": "2026-07-07T00:00:00+08:00",
                "end": "2026-07-07T23:59:59+08:00",
            },
            "includeLinkedPlans": True,
        },
    )

    assert [item["evtId"] for item in result["events"]] == ["plan-linked", "plan-free"]
    assert result["events"][0]["ddlLink"] == {
        "ddlEvtId": "ddl-1",
        "planRole": "one_day_before",
        "sortOrder": 0,
    }


def test_query_events_can_hide_storage_linked_plans(monkeypatch: pytest.MonkeyPatch) -> None:
    events = [
        {
            "evtId": "plan-linked",
            "evtType": "plan",
            "title": "自动计划",
            "stat": "todo",
            "stTime": "2026-07-07T20:00:00+08:00",
            "durationMin": 30,
        },
        {
            "evtId": "plan-free",
            "evtType": "plan",
            "title": "普通计划",
            "stat": "todo",
            "stTime": "2026-07-07T21:00:00+08:00",
            "durationMin": 30,
        },
    ]
    monkeypatch.setattr(routes.crud, "listEvt", lambda _db: events)
    db = _FakeDb([_Link("ddl-1", "plan-linked", "one_day_before", 0)])

    result = routes._query_events(db, {"includeLinkedPlans": False})

    assert [item["evtId"] for item in result["events"]] == ["plan-free"]


def test_query_events_rejects_reversed_range(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes.crud, "listEvt", lambda _db: [])
    db = _FakeDb([])

    with pytest.raises(ValueError, match="timeRange.start"):
        routes._query_events(
            db,
            {
                "timeRange": {
                    "start": "2026-07-08T00:00:00+08:00",
                    "end": "2026-07-07T00:00:00+08:00",
                }
            },
        )
