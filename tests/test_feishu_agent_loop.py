import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.agent import routes as agent_routes
from app.main import create_app


def _message_event(text: str, *, chat_id: str = "oc_user_chat", message_id: str = "om_1") -> dict:
    return {
        "schema": "2.0",
        "header": {"event_type": "im.message.receive_v1", "token": "verify-token"},
        "event": {
            "sender": {
                "sender_id": {
                    "open_id": "ou_sender",
                    "user_id": "u_sender",
                },
                "sender_type": "user",
            },
            "message": {
                "message_id": message_id,
                "chat_id": chat_id,
                "chat_type": "p2p",
                "message_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
        },
    }


class FakeFeishuClient:
    def __init__(self) -> None:
        self.text_calls: list[tuple[str, str]] = []
        self.card_calls: list[tuple[str, dict]] = []

    def send_text(self, receive_id: str, text: str, **kwargs) -> dict:
        self.text_calls.append((receive_id, text))
        return {"code": 0, "data": {"message_id": "om_reply"}}

    def send_interactive_card(self, receive_id: str, card: dict, **kwargs) -> dict:
        self.card_calls.append((receive_id, card))
        return {"code": 0, "data": {"message_id": "om_card"}}


def test_feishu_message_normalization_includes_routing_context(app_env, monkeypatch) -> None:
    forwarded: dict = {}

    def fake_post(url, **kwargs):
        forwarded["json"] = kwargs["json"]

        class Resp:
            is_error = False
            status_code = 200

        return Resp()

    monkeypatch.setenv("OPENCLAW_EVENTS_ENDPOINT", "http://openclaw.local/events")
    monkeypatch.setattr("httpx.post", fake_post)
    client = TestClient(create_app())

    resp = client.post("/feishu/event", json=_message_event("帮我记一下明天晚上洗衣服"))

    assert resp.status_code == 200
    event = forwarded["json"]
    assert event["eventType"] == "message"
    assert event["chat_id"] == "oc_user_chat"
    assert event["message_id"] == "om_1"
    assert event["text"] == "帮我记一下明天晚上洗衣服"
    assert event["chat"] == {"chat_id": "oc_user_chat", "chat_type": "p2p"}
    assert event["user"]["user_id"] == "u_sender"
    assert event["request"]["timezone"] == "Asia/Shanghai"
    assert "now" in event["request"]


def test_send_text_uses_default_chat_id(app_env, monkeypatch) -> None:
    fake_client = FakeFeishuClient()
    monkeypatch.setattr(agent_routes, "_feishuClient", fake_client)
    client = TestClient(create_app())
    headers = {"X-SmartCore-Agent-Token": "agent-secret"}

    resp = client.post(
        "/agent/sendText",
        headers=headers,
        json={"text": "已记录"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["stat"] == "done"
    assert fake_client.text_calls == [("oc_default", "已记录")]
    assert "tenant_access_token" not in json.dumps(body)
    assert "app-secret" not in json.dumps(body)


def test_send_text_uses_explicit_chat_id(app_env, monkeypatch) -> None:
    fake_client = FakeFeishuClient()
    monkeypatch.setattr(agent_routes, "_feishuClient", fake_client)
    client = TestClient(create_app())
    headers = {"X-SmartCore-Agent-Token": "agent-secret"}

    resp = client.post(
        "/agent/sendText",
        headers=headers,
        json={"text": "好的", "chatId": "oc_explicit"},
    )

    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert fake_client.text_calls == [("oc_explicit", "好的")]


def test_send_card_calls_feishu_interactive(app_env, monkeypatch) -> None:
    fake_client = FakeFeishuClient()
    monkeypatch.setattr(agent_routes, "_feishuClient", fake_client)
    card = {"schema": "2.0", "header": {"title": {"tag": "plain_text", "content": "提醒"}}, "elements": []}
    client = TestClient(create_app())
    headers = {"X-SmartCore-Agent-Token": "agent-secret"}

    resp = client.post(
        "/agent/sendCard",
        headers=headers,
        json={"chat_id": "oc_card", "card": card},
    )

    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert fake_client.card_calls[0][0] == "oc_card"
    assert fake_client.card_calls[0][1]["header"]["title"]["content"] == "提醒"


def test_agent_endpoints_return_ok_false_for_missing_ids(app_env) -> None:
    client = TestClient(create_app())
    headers = {"X-SmartCore-Agent-Token": "agent-secret"}

    for path, payload in (
        ("/agent/evtUpdate", {}),
        ("/agent/evtDelete", {}),
        ("/agent/ideaToEvt", {}),
    ):
        resp = client.post(path, headers=headers, json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert body["stat"] == "failed"
        assert body["errors"]


def test_openclaw_skill_requires_feishu_reply() -> None:
    skill = Path("openclaw/skills/smartcore/SKILL.md").read_text(encoding="utf-8")
    assert "sendText" in skill
    assert "sendCard" in skill
    assert "Every handled Feishu event must end with" in skill


def test_openclaw_adapter_prompt_requires_feishu_reply() -> None:
    adapter_source = Path("openclaw/adapter/adapter.py").read_text(encoding="utf-8")
    assert "POST /agent/sendText or POST /agent/sendCard" in adapter_source
    assert "event.chat_id" in adapter_source
