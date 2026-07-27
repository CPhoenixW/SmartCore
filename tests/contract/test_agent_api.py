from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest

from app.server.agent import routes
from app.server.agent.v2_routes import _normalize_query_body, _resolved_iso
from openclaw.skills.smartcore.scripts import call_tool, query_events

pytestmark = pytest.mark.contract


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
    assert tools["computerHourlyContext"]["path"] == "/agent/computer/hourly-context"
    assert tools["computerHourlyContext"]["method"] == "GET"
    assert tools["computerHourlyAnalysisComplete"]["path"] == "/agent/computer/hourly-analysis"
    assert tools["computerDailyContext"]["path"] == "/agent/computer/daily-context"
    assert tools["computerDailyLogComplete"]["path"] == "/agent/computer/daily-log"
    assert "mediaImageOcr" not in tools
    assert "ocrEvidence" not in tools["ideaCapture"]["inputSchema"]["properties"]
    assert tools["ideaMediaJobComplete"]["inputSchema"]["required"] == [
        "jobId",
        "summary",
    ]


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


def test_agent_normalizes_utc_and_naive_times_to_shanghai() -> None:
    context = {
        "timezone": "Asia/Shanghai",
        "request": {
            "timezone": "Asia/Shanghai",
            "now": "2026-07-08T10:00:00+08:00",
        },
    }

    assert (
        _resolved_iso(
            "2026-07-08T20:00:00Z",
            context,
            "stTime",
        )
        == "2026-07-09T04:00:00+08:00"
    )
    assert (
        _resolved_iso(
            "2026-07-08T20:00:00",
            context,
            "stTime",
        )
        == "2026-07-08T20:00:00+08:00"
    )


def test_agent_anchors_time_only_values_to_request_date() -> None:
    context = {
        "request": {
            "timezone": "Asia/Shanghai",
            "now": "2026-07-08T10:00:00+08:00",
        }
    }

    assert _resolved_iso("20:30", context, "stTime") == "2026-07-08T20:30:00+08:00"


def test_agent_rejects_unresolved_relative_text() -> None:
    with pytest.raises(ValueError, match="relative text"):
        _resolved_iso(
            "明天晚上八点",
            {
                "request": {
                    "timezone": "Asia/Shanghai",
                    "now": "2026-07-08T10:00:00+08:00",
                }
            },
            "stTime",
        )


def test_query_normalization_rejects_undocumented_range_fields() -> None:
    with pytest.raises(ValueError, match=r"end_time, start_time.*timeRange"):
        _normalize_query_body(
            {
                "start_time": "2026-07-20T00:00:00+08:00",
                "end_time": "2026-07-20T23:59:59+08:00",
            }
        )

    with pytest.raises(ValueError, match=r"filter.*timeRange"):
        _normalize_query_body(
            {
                "filter": {
                    "time_range": {
                        "start": "2026-07-20T00:00:00+08:00",
                        "end": "2026-07-20T23:59:59+08:00",
                    }
                }
            }
        )


def test_query_normalization_accepts_only_start_and_end_inside_time_range() -> None:
    normalized = _normalize_query_body(
        {
            "timeRange": {
                "start": "2026-07-20T00:00:00+08:00",
                "end": "2026-07-20T23:59:59+08:00",
            },
            "includeLinkedPlans": True,
        }
    )
    assert normalized["timeRange"] == {
        "start": "2026-07-20T00:00:00+08:00",
        "end": "2026-07-20T23:59:59+08:00",
    }

    with pytest.raises(ValueError, match="unsupported timeRange field"):
        _normalize_query_body({"timeRange": {"start_time": "2026-07-20"}})


def parse(*args: str):
    return query_events.parser().parse_args(args)


def test_single_day_query_body_uses_strict_contract() -> None:
    body = query_events.build_body(parse("--date", "2026-07-20"))

    assert body == {
        "date": "2026-07-20",
        "includeLinkedPlans": True,
        "includeCourseTemplates": False,
        "includeReminders": False,
        "limit": 100,
    }


def test_range_query_requires_both_boundaries() -> None:
    with pytest.raises(ValueError, match="provided together"):
        query_events.build_body(
            parse(
                "--start",
                "2026-07-20T00:00:00+08:00",
            )
        )


def test_query_helper_uses_token_scope_and_returns_api_json(tmp_path, monkeypatch) -> None:
    token_file = tmp_path / "token"
    token_file.write_text("agent-secret\n", encoding="utf-8")
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self) -> bytes:
            return b'{"ok":true,"data":{"items":[],"count":0,"total":0}}'

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setenv("SMARTCORE_AGENT_TOKEN_FILE", str(token_file))
    monkeypatch.setenv("SMARTCORE_BASE_URL", "http://smartcore.local/")
    monkeypatch.setattr(query_events.urllib.request, "urlopen", fake_urlopen)

    result = query_events.query_events(parse("--scope", "signed-scope", "--date", "2026-07-20"))

    request = captured["request"]
    assert result["ok"] is True
    assert request.full_url == "http://smartcore.local/agent/db/query_events"
    assert request.headers["X-smartcore-agent-token"] == "agent-secret"
    assert request.headers["X-smartcore-agent-scope"] == "signed-scope"
    assert json.loads(request.data)["date"] == "2026-07-20"
    assert captured["timeout"] == 15


def test_query_helper_uses_task_scope_environment(tmp_path, monkeypatch) -> None:
    token_file = tmp_path / "token"
    token_file.write_text("agent-secret\n", encoding="utf-8")
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self) -> bytes:
            return b'{"ok":true}'

    monkeypatch.setenv("SMARTCORE_AGENT_TOKEN_FILE", str(token_file))
    monkeypatch.setenv("SMARTCORE_AGENT_SCOPE", "task-scope")
    monkeypatch.setattr(
        query_events.urllib.request,
        "urlopen",
        lambda request, timeout: captured.update(request=request) or Response(),
    )

    result = query_events.query_events(parse("--date", "2026-07-20"))

    assert result["ok"] is True
    assert captured["request"].headers["X-smartcore-agent-scope"] == "task-scope"


def test_generic_tool_helper_discovers_path_without_exposing_credentials(
    tmp_path, monkeypatch
) -> None:
    token_file = tmp_path / "token"
    token_file.write_text("agent-secret\n", encoding="utf-8")
    scope_file = tmp_path / "scope"
    scope_file.write_text("signed-scope\n", encoding="utf-8")
    requests = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self) -> bytes:
            return json.dumps(self.payload).encode()

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        if request.full_url.endswith("/agent/tools"):
            return Response(
                {
                    "ok": True,
                    "data": {
                        "tools": [
                            {
                                "name": "ideaCapture",
                                "method": "POST",
                                "path": "/agent/idea/capture",
                            }
                        ]
                    },
                }
            )
        return Response({"ok": True, "data": {"ideaId": "idea-1"}})

    monkeypatch.setenv("SMARTCORE_AGENT_TOKEN_FILE", str(token_file))
    monkeypatch.setenv("SMARTCORE_BASE_URL", "http://smartcore.local/")
    monkeypatch.setattr(call_tool.urllib.request, "urlopen", fake_urlopen)
    args = call_tool.parser().parse_args(
        [
            "--scope-file",
            str(scope_file),
            "--tool",
            "ideaCapture",
            "--body-json",
            '{"title":"视觉记录"}',
        ]
    )

    result = call_tool.call_tool(args)

    assert result["ok"] is True
    request = requests[1][0]
    assert request.full_url == "http://smartcore.local/agent/idea/capture"
    assert request.headers["X-smartcore-agent-token"] == "agent-secret"
    assert request.headers["X-smartcore-agent-scope"] == "signed-scope"
    assert json.loads(request.data) == {"title": "视觉记录"}


def test_generic_tool_helper_accepts_unique_published_path_suffix(
    tmp_path, monkeypatch
) -> None:
    token_file = tmp_path / "token"
    token_file.write_text("agent-secret\n", encoding="utf-8")
    scope_file = tmp_path / "scope"
    scope_file.write_text("signed-scope\n", encoding="utf-8")
    requests = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self) -> bytes:
            return json.dumps(self.payload).encode()

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        if request.full_url.endswith("/agent/tools"):
            return Response(
                {
                    "ok": True,
                    "data": {
                        "tools": [
                            {
                                "name": "evtUpdate",
                                "method": "POST",
                                "path": "/agent/db/update_event",
                            }
                        ]
                    },
                }
            )
        return Response({"ok": True, "stat": "done"})

    monkeypatch.setenv("SMARTCORE_AGENT_TOKEN_FILE", str(token_file))
    monkeypatch.setenv("SMARTCORE_BASE_URL", "http://smartcore.local/")
    monkeypatch.setattr(call_tool.urllib.request, "urlopen", fake_urlopen)
    args = call_tool.parser().parse_args(
        [
            "--scope-file",
            str(scope_file),
            "--tool",
            "update_event",
            "--body-json",
            '{"evtId":"plan-1","stTime":"2026-07-27T11:00:00+08:00"}',
        ]
    )

    result = call_tool.call_tool(args)

    assert result["ok"] is True
    request = requests[1][0]
    assert request.full_url == "http://smartcore.local/agent/db/update_event"
    assert json.loads(request.data) == {
        "evtId": "plan-1",
        "stTime": "2026-07-27T11:00:00+08:00",
    }


def test_generic_tool_helper_encodes_get_tool_arguments(tmp_path, monkeypatch) -> None:
    token_file = tmp_path / "token"
    token_file.write_text("agent-secret\n", encoding="utf-8")
    scope_file = tmp_path / "scope"
    scope_file.write_text("signed-scope\n", encoding="utf-8")
    requests = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self) -> bytes:
            return json.dumps(self.payload).encode()

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        if request.full_url.endswith("/agent/tools"):
            return Response(
                {
                    "ok": True,
                    "data": {
                        "tools": [
                            {
                                "name": "computerHourlyContext",
                                "method": "GET",
                                "path": "/agent/computer/hourly-context",
                            }
                        ]
                    },
                }
            )
        return Response({"ok": True, "data": {"activeSeconds": 120}})

    monkeypatch.setenv("SMARTCORE_AGENT_TOKEN_FILE", str(token_file))
    monkeypatch.setenv("SMARTCORE_BASE_URL", "http://smartcore.local/")
    monkeypatch.setattr(call_tool.urllib.request, "urlopen", fake_urlopen)
    args = call_tool.parser().parse_args(
        [
            "--scope-file",
            str(scope_file),
            "--tool",
            "computerHourlyContext",
            "--body-json",
            '{"deviceId":"computer-1","hourStart":"2026-07-27T08:00:00+00:00"}',
        ]
    )

    result = call_tool.call_tool(args)

    assert result["ok"] is True
    request = requests[1][0]
    assert request.method == "GET"
    assert request.data is None
    assert "deviceId=computer-1" in request.full_url
    assert "hourStart=2026-07-27T08%3A00%3A00%2B00%3A00" in request.full_url


def test_runtime_config_supplies_base_url_and_token_path(tmp_path, monkeypatch) -> None:
    skill_root = tmp_path / "smartcore"
    script = skill_root / "scripts" / "query_events.py"
    script.parent.mkdir(parents=True)
    script.write_text("", encoding="utf-8")
    runtime_file = skill_root / "runtime.json"
    runtime_file.write_text(
        json.dumps(
            {
                "base_url": "http://smartcore.runtime:8000",
                "token_file": "/runtime/token",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(query_events, "__file__", str(script))

    assert query_events.runtime_config() == {
        "base_url": "http://smartcore.runtime:8000",
        "token_file": "/runtime/token",
    }
