from __future__ import annotations

import json

import pytest

from app.server.agent import routes
from app.server.agent.v2_routes import (
    _normalize_query_body,
    _resolved_absolute_iso,
    _resolved_iso,
)
from openclaw.skills.smartcore.scripts import call_tool, query_events

pytestmark = pytest.mark.contract


def test_agent_tools_keep_stable_names_and_canonical_paths() -> None:
    tools = {item["name"]: item for item in routes._AGENT_TOOLS}

    assert tools["dailyWorkContext"]["path"] == "/agent/daily-work-context"
    assert tools["dailyWorkContext"]["method"] == "GET"
    assert tools["evtQuery"]["path"] == "/agent/db/query_events"
    assert "legacyPaths" not in tools["evtQuery"]
    assert tools["evtCreate"]["path"] == "/agent/db/create_event"
    assert tools["evtUpdate"]["path"] == "/agent/db/update_event"
    assert all("legacyPaths" not in tool for tool in tools.values())
    assert tools["commutePlanUpdate"]["path"] == "/agent/db/update_commute_plan"
    assert tools["commutePlanUpdate"]["inputSchema"]["required"] == [
        "planEvtId",
        "reminderEvtId",
        "departureAt",
        "commuteMinutes",
        "endAt",
    ]
    assert tools["evtDelete"]["path"] == "/agent/db/delete_event"
    assert not any(name.startswith("send") for name in tools)
    assert tools["computerHourlyContext"]["path"] == "/agent/computer/hourly-context"
    assert tools["computerHourlyContext"]["method"] == "GET"
    assert tools["computerHourlyAnalysisComplete"]["path"] == "/agent/computer/hourly-analysis"
    assert tools["computerDailyContext"]["path"] == "/agent/computer/daily-context"
    assert tools["computerDailyLogComplete"]["path"] == "/agent/computer/daily-log"
    assert tools["computerWorkBlockContext"]["path"] == "/agent/computer/work-block-context"
    assert tools["computerWorkBlockAnalysisComplete"]["path"] == "/agent/computer/work-block-analysis"
    for name in (
        "computerHourlyAnalysisComplete",
        "computerDailyLogComplete",
        "computerWorkBlockAnalysisComplete",
    ):
        assert tools[name]["inputSchema"]["properties"]["model"]["enum"] == [
            "qwen3.7-plus",
            "deepseek-v4-flash",
            "deepseek-v4-flash-0731",
        ]
    assert (
        tools["computerWorkBlockAnalysisComplete"]["inputSchema"]["properties"]["title"][
            "maxLength"
        ]
        == 20
    )
    assert "mediaImageOcr" not in tools
    assert "ocrEvidence" not in tools["ideaCapture"]["inputSchema"]["properties"]
    assert tools["ideaMediaJobComplete"]["inputSchema"]["required"] == [
        "jobId",
        "summary",
    ]


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


def test_commute_times_require_absolute_offsets() -> None:
    body = {"timezone": "Asia/Shanghai"}
    assert (
        _resolved_absolute_iso("2026-08-01T14:00:00+08:00", body, "departureAt")
        == "2026-08-01T14:00:00+08:00"
    )
    with pytest.raises(ValueError, match="include a UTC offset"):
        _resolved_absolute_iso("2026-08-01T14:00:00", body, "departureAt")


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

    with pytest.raises(ValueError, match="timeRange.start"):
        _normalize_query_body(
            {
                "timeRange": {
                    "start": "2026-07-21T00:00:00+08:00",
                    "end": "2026-07-20T00:00:00+08:00",
                }
            }
        )


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
