import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.agent.scope import issue_agent_scope
from app.db.session import SessionLocal
from app.feishu.client import FeishuClient
from app.main import create_app
from app.new_core.models import FeishuBind, FeishuBot, LifeIdentity


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


def _image_event(*, chat_id: str = "oc_user_chat", message_id: str = "om_image") -> dict:
    event = _message_event("", chat_id=chat_id, message_id=message_id)
    event["event"]["message"] = {
        "message_id": message_id,
        "chat_id": chat_id,
        "chat_type": "p2p",
        "message_type": "image",
        "content": json.dumps({"image_key": "img_test"}),
    }
    return event


def _post_image_event(*, chat_id: str = "oc_user_chat", message_id: str = "om_post_image") -> dict:
    event = _message_event("", chat_id=chat_id, message_id=message_id)
    event["event"]["message"] = {
        "message_id": message_id, "chat_id": chat_id, "chat_type": "p2p", "message_type": "post",
        "content": json.dumps({"post": {"zh_cn": {"title": "", "content": [[
            {"tag": "text", "text": "这个想法记一下："}, {"tag": "img", "image_key": "img_post"}
        ]]}}}),
    }
    return event


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


def _bind_default_chat(chat_id: str) -> str:
    db = SessionLocal()
    try:
        bot = db.query(FeishuBot).one()
        identity = LifeIdentity(userId="default", provider="feishu", externalId="ou_sender")
        db.add(identity)
        db.flush()
        db.add(FeishuBind(userId="default", botId=bot.botId, identityId=identity.identityId, chatId=chat_id, isPrimary=True))
        db.commit()
        return issue_agent_scope(userId="default", botId=bot.botId, chatId=chat_id)
    finally:
        db.close()


def test_feishu_message_normalization_includes_routing_context(app_env, monkeypatch) -> None:
    forwarded: dict = {}
    acknowledgements: list[tuple[str, str]] = []
    operations: list[str] = []

    def fake_post(url, **kwargs):
        operations.append("forward")
        forwarded["json"] = kwargs["json"]

        class Resp:
            is_error = False
            status_code = 200

        return Resp()

    monkeypatch.setenv("OPENCLAW_EVENTS_ENDPOINT", "http://openclaw.local/events")
    monkeypatch.setattr("httpx.post", fake_post)
    monkeypatch.setattr(
        FeishuClient,
        "send_text",
        lambda _self, chat_id, text, **_kwargs: (
            operations.append("ack") or acknowledgements.append((chat_id, text)) or {"code": 0}
        ),
    )
    client = TestClient(create_app())
    _bind_default_chat("oc_user_chat")

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
    assert isinstance(event["agentScope"], str) and event["agentScope"]
    assert acknowledgements == [("oc_user_chat", "已收到，正在处理…")]
    assert operations == ["ack", "forward"]


def test_feishu_processing_ack_failure_does_not_block_openclaw_forward(app_env, monkeypatch) -> None:
    forwarded: dict = {}

    def fake_post(_url, **kwargs):
        forwarded["json"] = kwargs["json"]

        class Resp:
            is_error = False
            status_code = 200

        return Resp()

    def fail_ack(*_args, **_kwargs):
        raise RuntimeError("unavailable")

    monkeypatch.setenv("OPENCLAW_EVENTS_ENDPOINT", "http://openclaw.local/events")
    monkeypatch.setattr("httpx.post", fake_post)
    monkeypatch.setattr(FeishuClient, "send_text", fail_ack)
    client = TestClient(create_app())
    _bind_default_chat("oc_user_chat")

    response = client.post("/feishu/event", json=_message_event("测试", message_id="om_ack_failure"))

    assert response.status_code == 200
    assert response.json()["msg"] == "ok"
    assert forwarded["json"]["message_id"] == "om_ack_failure"


def test_feishu_image_is_analyzed_by_vision_model_then_forwarded(app_env, monkeypatch) -> None:
    forwarded: dict = {}

    def fake_post(_url, **kwargs):
        forwarded["json"] = kwargs["json"]

        class Resp:
            is_error = False
            status_code = 200

        return Resp()

    monkeypatch.setenv("OPENCLAW_EVENTS_ENDPOINT", "http://openclaw.local/events")
    monkeypatch.setattr("httpx.post", fake_post)
    monkeypatch.setattr(
        FeishuClient,
        "download_message_resource",
        lambda _self, message_id, resource_key: (b"test-image", "image/png"),
    )
    monkeypatch.setattr(
        "app.feishu.event_handler.analyze_image",
        lambda image, **kwargs: "OCR：课程作业，明晚 20:00 前提交。",
    )
    monkeypatch.setattr(FeishuClient, "send_text", lambda *_args, **_kwargs: {"code": 0})
    client = TestClient(create_app())
    _bind_default_chat("oc_user_chat")

    response = client.post("/feishu/event", json=_image_event())

    assert response.status_code == 200
    event = forwarded["json"]
    assert event["imageAnalysis"] == "OCR：课程作业，明晚 20:00 前提交。"
    assert "图像解析结果" in event["text"]
    assert event["message"]["image_analysis"] == event["imageAnalysis"]


def test_feishu_post_with_image_is_analyzed_and_keeps_its_text(app_env, monkeypatch) -> None:
    forwarded: dict = {}

    def fake_post(_url, **kwargs):
        forwarded["json"] = kwargs["json"]

        class Resp:
            is_error = False
            status_code = 200

        return Resp()

    monkeypatch.setenv("OPENCLAW_EVENTS_ENDPOINT", "http://openclaw.local/events")
    monkeypatch.setattr("httpx.post", fake_post)
    monkeypatch.setattr(FeishuClient, "download_message_resource", lambda *_args: (b"image", "image/png"))
    monkeypatch.setattr("app.feishu.event_handler.analyze_image", lambda *_args, **_kwargs: "一张产品草图")
    monkeypatch.setattr(FeishuClient, "send_text", lambda *_args, **_kwargs: {"code": 0})
    client = TestClient(create_app())
    _bind_default_chat("oc_user_chat")

    assert client.post("/feishu/event", json=_post_image_event()).status_code == 200
    assert "这个想法记一下：" in forwarded["json"]["text"]
    assert forwarded["json"]["imageAnalysis"] == "一张产品草图"


def test_scoped_send_text_uses_bound_chat_only(app_env, monkeypatch) -> None:
    fake_client = FakeFeishuClient()
    monkeypatch.setattr(FeishuClient, "send_interactive_card", fake_client.send_interactive_card)
    client = TestClient(create_app())
    scope = _bind_default_chat("oc_bound")
    headers = {"X-SmartCore-Agent-Token": "agent-secret", "X-SmartCore-Agent-Scope": scope}

    resp = client.post(
        "/agent/sendText",
        headers=headers,
        json={"text": "**已记录**\n- 事项一", "chatId": "oc_wrong"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["stat"] == "done"
    assert fake_client.text_calls == []
    assert fake_client.card_calls[0][0] == "oc_bound"
    markdown = fake_client.card_calls[0][1]["elements"][0]["text"]
    assert markdown == {"tag": "lark_md", "content": "**已记录**\n- 事项一"}
    assert "tenant_access_token" not in json.dumps(body)
    assert "app-secret" not in json.dumps(body)


def test_send_card_calls_feishu_interactive(app_env, monkeypatch) -> None:
    fake_client = FakeFeishuClient()
    monkeypatch.setattr(FeishuClient, "send_interactive_card", fake_client.send_interactive_card)
    card = {"schema": "2.0", "header": {"title": {"tag": "plain_text", "content": "提醒"}}, "elements": []}
    client = TestClient(create_app())
    scope = _bind_default_chat("oc_bound")
    headers = {"X-SmartCore-Agent-Token": "agent-secret", "X-SmartCore-Agent-Scope": scope}

    resp = client.post(
        "/agent/sendCard",
        headers=headers,
        json={"chat_id": "oc_wrong", "card": card},
    )

    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert fake_client.card_calls[0][0] == "oc_bound"
    assert fake_client.card_calls[0][1]["header"]["title"]["content"] == "提醒"


def test_agent_endpoints_return_ok_false_for_missing_ids(app_env) -> None:
    client = TestClient(create_app())
    scope = _bind_default_chat("oc_bound")
    headers = {"X-SmartCore-Agent-Token": "agent-secret", "X-SmartCore-Agent-Scope": scope}

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


def test_scoped_create_ignores_caller_supplied_user_id(app_env) -> None:
    client = TestClient(create_app())
    scope = _bind_default_chat("oc_bound")
    headers = {"X-SmartCore-Agent-Token": "agent-secret", "X-SmartCore-Agent-Scope": scope}

    response = client.post(
        "/agent/db/create_event",
        headers=headers,
        json={"evtType": "plan", "title": "只属于默认用户", "stTime": "2026-07-17T10:00:00+08:00", "userId": "other"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["userId"] == "default"


def test_scoped_query_rejects_silent_full_scan_fields(app_env) -> None:
    client = TestClient(create_app())
    scope = _bind_default_chat("oc_bound")
    headers = {"X-SmartCore-Agent-Token": "agent-secret", "X-SmartCore-Agent-Scope": scope}

    response = client.post(
        "/agent/db/query_events",
        headers=headers,
        json={
            "start_time": "2026-07-20T00:00:00+08:00",
            "end_time": "2026-07-20T23:59:59+08:00",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert "use date or timeRange.start/timeRange.end" in body["errors"][0]


def test_openclaw_skill_delegates_feishu_reply_to_adapter() -> None:
    skill = Path("openclaw/skills/smartcore/SKILL.md").read_text(encoding="utf-8")
    assert "Adapter sends that text" in skill
    assert "X-SmartCore-Agent-Scope" in skill
    assert "Do not call `sendFeishuText`" in skill
    assert "`--date YYYY-MM-DD`" in skill
    assert "`--start`" in skill
    assert "`data.items`" in skill
    assert "`start_time`" in skill
    assert "Do not pipe a response through `head`" in skill
    assert "Filtering & Anti-Noise Rules" in skill
    assert "scripts/query_events.py" in skill


def test_openclaw_adapter_prompt_owns_feishu_reply() -> None:
    adapter_source = Path("openclaw/adapter/adapter.py").read_text(encoding="utf-8")
    assert "X-SmartCore-Agent-Scope" in adapter_source
    assert "the Adapter owns final delivery" in adapter_source
    assert "/agent/feedback/send_text" in adapter_source
    assert "timeRange.start and timeRange.end" in adapter_source
    assert "data.items" in adapter_source
    assert "scripts/smartcore/scripts/query_events.py" not in adapter_source
    assert "skills/smartcore/scripts/query_events.py" in adapter_source
