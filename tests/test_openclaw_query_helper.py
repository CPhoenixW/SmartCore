from __future__ import annotations

import json

import pytest

from openclaw.skills.smartcore.scripts import query_events


def parse(*args: str):
    return query_events.parser().parse_args(args)


def test_single_day_query_body_uses_strict_contract() -> None:
    body = query_events.build_body(parse("--scope", "scope", "--date", "2026-07-20"))

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
                "--scope",
                "scope",
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
