import json
import subprocess

from openclaw.adapter import adapter


class FakeResponse:
    def __init__(self, body: dict):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return json.dumps(self.body).encode()


def test_send_final_reply_uses_token_and_scope_without_target_ids(tmp_path, monkeypatch) -> None:
    token_file = tmp_path / "token"
    token_file.write_text("agent-secret\n", encoding="utf-8")
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse({"ok": True})

    monkeypatch.setenv("SMARTCORE_BASE_URL", "http://smartcore.local/")
    monkeypatch.setenv("SMARTCORE_AGENT_TOKEN_FILE", str(token_file))
    monkeypatch.setattr(adapter.urllib.request, "urlopen", fake_urlopen)

    adapter.send_final_reply(
        {"agentScope": "signed-scope", "chat_id": "must-not-be-sent"},
        "最终答案",
    )

    request = captured["request"]
    assert request.full_url == "http://smartcore.local/agent/feedback/send_text"
    assert json.loads(request.data) == {"text": "最终答案"}
    assert request.headers["X-smartcore-agent-token"] == "agent-secret"
    assert request.headers["X-smartcore-agent-scope"] == "signed-scope"
    assert b"must-not-be-sent" not in request.data
    assert captured["timeout"] == 15


def test_run_openclaw_delivers_generated_final_text(monkeypatch) -> None:
    delivered = []
    logs = []
    payload = {"result": {"finalAssistantVisibleText": "昨天没有安排。"}}

    monkeypatch.setattr(
        adapter.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=["openclaw"],
            returncode=0,
            stdout=json.dumps(payload, ensure_ascii=False),
            stderr="",
        ),
    )
    monkeypatch.setattr(
        adapter,
        "send_final_reply",
        lambda event, text: delivered.append((event, text)),
    )
    monkeypatch.setattr(adapter, "log", lambda message, **fields: logs.append((message, fields)))

    event = {"event_id": "evt-1", "agentScope": "scope"}
    adapter.run_openclaw(event)

    assert delivered == [(event, "昨天没有安排。")]
    assert any(message == "final reply delivered" for message, _fields in logs)
    finished = next(fields for message, fields in logs if message == "openclaw finished")
    assert finished["reply_delivered"] is True


def test_run_openclaw_failure_sends_failure_reply(monkeypatch) -> None:
    delivered = []

    monkeypatch.setattr(
        adapter.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=["openclaw"],
            returncode=1,
            stdout="",
            stderr="provider unavailable",
        ),
    )
    monkeypatch.setattr(
        adapter,
        "send_final_reply",
        lambda event, text: delivered.append((event, text)),
    )
    monkeypatch.setattr(adapter, "log", lambda *_args, **_kwargs: None)

    event = {"event_id": "evt-2", "agentScope": "scope"}
    adapter.run_openclaw(event)

    assert delivered == [(event, adapter.FAILURE_REPLY)]


def test_delivery_failure_is_logged_without_raising(monkeypatch) -> None:
    logs = []
    monkeypatch.setattr(
        adapter,
        "send_final_reply",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("rejected")),
    )
    monkeypatch.setattr(adapter, "log", lambda message, **fields: logs.append((message, fields)))

    assert adapter.deliver_reply({"event_id": "evt-3"}, "answer") is False
    assert logs == [
        (
            "final reply failed",
            {"event_id": "evt-3", "error": "RuntimeError('rejected')"},
        )
    ]


def test_sync_bundled_skill_updates_workspace_atomically(tmp_path, monkeypatch) -> None:
    source = tmp_path / "bundled" / "SKILL.md"
    source.parent.mkdir()
    source.write_text("new contract\n", encoding="utf-8")
    source_script = source.parent / "scripts" / "query_events.py"
    source_script.parent.mkdir()
    source_script.write_text("print('query')\n", encoding="utf-8")
    workspace = tmp_path / "workspace"
    target = workspace / "skills" / "smartcore" / "SKILL.md"
    target.parent.mkdir(parents=True)
    target.write_text("stale contract\n", encoding="utf-8")

    monkeypatch.setenv("SMARTCORE_BUNDLED_SKILL", str(source))
    monkeypatch.setenv("OPENCLAW_WORKSPACE", str(workspace))

    assert adapter.sync_bundled_skill() is True
    assert target.read_text(encoding="utf-8") == "new contract\n"
    assert (target.parent / "scripts" / "query_events.py").read_text(encoding="utf-8") == "print('query')\n"
    assert adapter.sync_bundled_skill() is False
    assert not (target.parent / ".SKILL.md.tmp").exists()
