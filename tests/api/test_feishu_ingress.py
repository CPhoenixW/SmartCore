from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.server.agent.scope import issue_agent_scope
from app.server.db.session import SessionLocal
from app.server.feishu.client import FeishuClient
from app.server.main import create_app
from app.server.new_core.event_relations import create_plan_event
from app.server.new_core.models import (
    EvtBase,
    FeishuBind,
    FeishuBot,
    LifeIdentity,
    MsgLog,
    PlanCompletionPrompt,
)
from app.server.new_core.plan_completion import dispatch_plan_completion_prompts

pytestmark = pytest.mark.api
REPO_ROOT = Path(__file__).resolve().parents[2]


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
        "message_id": message_id,
        "chat_id": chat_id,
        "chat_type": "p2p",
        "message_type": "post",
        "content": json.dumps(
            {
                "post": {
                    "zh_cn": {
                        "title": "",
                        "content": [
                            [
                                {"tag": "text", "text": "这个想法记一下："},
                                {"tag": "img", "image_key": "img_post"},
                            ]
                        ],
                    }
                }
            }
        ),
    }
    return event


def _post_media_event(*, chat_id: str = "oc_user_chat", message_id: str = "om_post_media") -> dict:
    event = _message_event("", chat_id=chat_id, message_id=message_id)
    event["event"]["message"] = {
        "message_id": message_id,
        "chat_id": chat_id,
        "chat_type": "p2p",
        "message_type": "post",
        "content": json.dumps(
            {
                "post": {
                    "zh_cn": {
                        "title": "",
                        "content": [
                            [
                                {"tag": "text", "text": "把这两张图记成灵感"},
                                {"tag": "img", "image_key": "img_one"},
                                {"tag": "img", "image_key": "img_two"},
                            ]
                        ],
                    }
                }
            }
        ),
    }
    return event


def _received_post_media_event(
    *, chat_id: str = "oc_user_chat", message_id: str = "om_received_post_media"
) -> dict:
    """Match the content shape emitted by im.message.receive_v1 for a post."""
    event = _message_event("", chat_id=chat_id, message_id=message_id)
    event["header"]["event_id"] = "evt_received_post_media"
    rows = [
        [{"tag": "text", "text": "这张图重点是今天的面试，给我安排好", "style": []}],
        [{"tag": "img", "image_key": "img_received", "width": 1084, "height": 2412}],
    ]
    event["event"]["message"] = {
        "message_id": message_id,
        "chat_id": chat_id,
        "chat_type": "p2p",
        "message_type": "post",
        "content": json.dumps(
            {"title": "", "content": rows, "content_v2": rows}, ensure_ascii=False
        ),
    }
    return event


def _file_event(*, chat_id: str = "oc_user_chat", message_id: str = "om_file") -> dict:
    event = _message_event("", chat_id=chat_id, message_id=message_id)
    event["event"]["message"] = {
        "message_id": message_id,
        "chat_id": chat_id,
        "chat_type": "p2p",
        "message_type": "file",
        "content": json.dumps({"file_key": "file_test", "file_name": "notes.pdf"}),
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
        db.add(
            FeishuBind(
                userId="default",
                botId=bot.botId,
                identityId=identity.identityId,
                chatId=chat_id,
                isPrimary=True,
            )
        )
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


def test_feishu_processing_ack_failure_does_not_block_openclaw_forward(
    app_env, monkeypatch
) -> None:
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

    response = client.post(
        "/feishu/event", json=_message_event("测试", message_id="om_ack_failure")
    )

    assert response.status_code == 200
    assert response.json()["msg"] == "ok"
    assert forwarded["json"]["message_id"] == "om_ack_failure"


def test_plan_completion_reply_is_bound_to_its_outbound_card(app_env, monkeypatch) -> None:
    """Only a reply to the stored card appends a Plan result; no Agent call occurs."""

    monkeypatch.setattr(
        FeishuClient,
        "send_interactive_card",
        lambda *_args, **_kwargs: {"code": 0, "data": {"message_id": "om_plan_card"}},
    )
    client = TestClient(create_app())
    _bind_default_chat("oc_plan_result")
    now = datetime(2026, 7, 30, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    db = SessionLocal()
    try:
        plan = create_plan_event(
            db,
            title="完成日报",
            stTime=(now - timedelta(minutes=30)).isoformat(),
            durationMin=30,
        )
        assert dispatch_plan_completion_prompts(db, now=now) == {"sent": 1, "failed": 0}
        prompt = db.query(PlanCompletionPrompt).one()
        assert prompt.outboundMessageId == "om_plan_card"
    finally:
        db.close()

    reply = _message_event("完成接口与回归测试", chat_id="oc_plan_result", message_id="om_result")
    reply["event"]["message"]["parent_id"] = "om_plan_card"
    response = client.post("/feishu/event", json=reply)
    duplicate = client.post("/feishu/event", json=reply)

    assert response.status_code == 200
    assert response.json()["msg"] == "plan completion reply processed"
    assert duplicate.status_code == 200
    db = SessionLocal()
    try:
        prompt = db.query(PlanCompletionPrompt).one()
        plan_base = db.get(EvtBase, plan["evtId"])
        assert prompt.stat == "answered"
        assert plan_base is not None and plan_base.desc == "执行结果：完成接口与回归测试"
        assert plan_base.stat == "todo"
    finally:
        db.close()


def test_plan_completion_card_action_marks_only_the_bound_plan_done(app_env, monkeypatch) -> None:
    monkeypatch.setattr(
        FeishuClient,
        "send_interactive_card",
        lambda *_args, **_kwargs: {"code": 0, "data": {"message_id": "om_plan_done"}},
    )
    client = TestClient(create_app())
    _bind_default_chat("oc_plan_done")
    now = datetime(2026, 7, 30, 13, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    db = SessionLocal()
    try:
        plan = create_plan_event(
            db,
            title="完成卡片",
            stTime=(now - timedelta(minutes=30)).isoformat(),
            durationMin=30,
        )
        dispatch_plan_completion_prompts(db, now=now)
        prompt = db.query(PlanCompletionPrompt).one()
    finally:
        db.close()

    action_event = {
        "schema": "2.0",
        "header": {
            "event_type": "card.action.trigger",
            "event_id": "evt_plan_done",
            "token": "verify-token",
        },
        "event": {
            "action": {
                "value": {
                    "kind": "planCompletionPrompt",
                    "promptId": prompt.promptId,
                    "evtId": plan["evtId"],
                    "action": "complete",
                }
            },
            "context": {"open_chat_id": "oc_plan_done", "open_message_id": "om_plan_done"},
            "operator": {"operator_id": {"open_id": "ou_sender"}},
        },
    }
    first = client.post("/feishu/event", json=action_event)
    second = client.post("/feishu/event", json=action_event)

    assert first.status_code == 200
    assert first.json()["toast"]["type"] == "success"
    assert second.json()["toast"]["type"] == "error"
    db = SessionLocal()
    try:
        prompt = db.query(PlanCompletionPrompt).one()
        plan_base = db.get(EvtBase, plan["evtId"])
        assert prompt.stat == "answered"
        assert plan_base is not None and plan_base.stat == "done"
        assert plan_base.desc == "执行结果：已完成"
    finally:
        db.close()

def test_feishu_image_is_forwarded_with_private_attachment(app_env, monkeypatch) -> None:
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
    monkeypatch.setattr(FeishuClient, "send_text", lambda *_args, **_kwargs: {"code": 0})
    client = TestClient(create_app())
    _bind_default_chat("oc_user_chat")

    response = client.post("/feishu/event", json=_image_event())

    assert response.status_code == 200
    assert forwarded["json"]["attachments"][0]["mimeType"] == "image/png"
    assert forwarded["json"]["attachments"][0]["agentPath"].startswith("/attachments/")


def test_feishu_image_pairs_recent_text_from_the_same_user(app_env, monkeypatch) -> None:
    forwarded: list[dict] = []

    def fake_post(_url, **kwargs):
        forwarded.append(kwargs["json"])

        class Resp:
            is_error = False
            status_code = 200

        return Resp()

    monkeypatch.setenv("OPENCLAW_EVENTS_ENDPOINT", "http://openclaw.local/events")
    monkeypatch.setattr("httpx.post", fake_post)
    monkeypatch.setattr(
        FeishuClient,
        "download_message_resource",
        lambda _self, _message_id, _resource_key: (b"test-image", "image/png"),
    )
    monkeypatch.setattr(FeishuClient, "send_text", lambda *_args, **_kwargs: {"code": 0})
    client = TestClient(create_app())
    _bind_default_chat("oc_user_chat")

    assert (
        client.post(
            "/feishu/event", json=_message_event("重点是明天的面试", message_id="om_context")
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/feishu/event", json=_image_event(message_id="om_image_with_context")
        ).status_code
        == 200
    )
    assert forwarded[-1]["text"] == "重点是明天的面试"


def test_feishu_post_with_image_is_forwarded(app_env, monkeypatch) -> None:
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
        FeishuClient, "download_message_resource", lambda *_args: (b"image", "image/png")
    )
    monkeypatch.setattr(FeishuClient, "send_text", lambda *_args, **_kwargs: {"code": 0})
    client = TestClient(create_app())
    _bind_default_chat("oc_user_chat")

    assert client.post("/feishu/event", json=_post_image_event()).status_code == 200
    assert forwarded["json"]["attachments"][0]["fileName"] == "feishu-image.png"


def test_feishu_post_with_multiple_images_and_text_is_forwarded(app_env, monkeypatch) -> None:
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
        FeishuClient, "download_message_resource", lambda *_args, **_kwargs: (b"image", "image/png")
    )
    monkeypatch.setattr(FeishuClient, "send_text", lambda *_args, **_kwargs: {"code": 0})
    client = TestClient(create_app())
    _bind_default_chat("oc_user_chat")

    assert client.post("/feishu/event", json=_post_media_event()).status_code == 200
    assert forwarded["json"]["text"].startswith("把这两张图记成灵感")
    assert len(forwarded["json"]["attachments"]) == 2


def test_feishu_received_post_with_image_and_text_is_forwarded(app_env, monkeypatch) -> None:
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
        lambda *_args, **_kwargs: (b"image", "image/jpeg"),
    )
    monkeypatch.setattr(FeishuClient, "send_text", lambda *_args, **_kwargs: {"code": 0})
    client = TestClient(create_app())
    _bind_default_chat("oc_user_chat")

    response = client.post("/feishu/event", json=_received_post_media_event())

    assert response.status_code == 200
    assert forwarded["json"]["text"] == "这张图重点是今天的面试，给我安排好"
    assert forwarded["json"]["attachments"][0]["fileName"] == "feishu-image.jpg"
    assert forwarded["json"]["feishu_payload"]["header"]["event_id"] == "evt_received_post_media"


def test_unsupported_feishu_message_is_logged_and_deduplicated(app_env, monkeypatch) -> None:
    replies: list[str] = []
    monkeypatch.setenv("OPENCLAW_EVENTS_ENDPOINT", "http://openclaw.local/events")
    event = _message_event("", message_id="om_sticker")
    event["header"]["event_id"] = "evt_sticker"
    event["event"]["message"]["message_type"] = "sticker"
    event["event"]["message"]["content"] = json.dumps({"file_key": "sticker_key"})
    monkeypatch.setattr(
        FeishuClient,
        "send_text",
        lambda _self, _chat_id, text, **_kwargs: replies.append(text) or {"code": 0},
    )
    client = TestClient(create_app())
    _bind_default_chat("oc_user_chat")

    first = client.post("/feishu/event", json=event)
    second = client.post("/feishu/event", json=event)

    assert first.status_code == 200
    assert first.json()["msg"] == "unsupported message type"
    assert second.json()["msg"] == "duplicate message ignored"
    assert len(replies) == 1
    db = SessionLocal()
    try:
        row = db.query(MsgLog).filter(MsgLog.externalId == "om_sticker").one()
        assert row.intent == "unsupported_message"
        assert row.stat == "unsupported:sticker"
    finally:
        db.close()


def test_feishu_file_is_forwarded_with_private_attachment(app_env, monkeypatch) -> None:
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
        lambda *_args, **_kwargs: (b"pdf", "application/pdf"),
    )
    monkeypatch.setattr(FeishuClient, "send_text", lambda *_args, **_kwargs: {"code": 0})
    client = TestClient(create_app())
    _bind_default_chat("oc_user_chat")

    assert client.post("/feishu/event", json=_file_event()).status_code == 200
    assert forwarded["json"]["attachments"][0]["fileName"] == "notes.pdf"
    assert forwarded["json"]["attachments"][0]["mimeType"] == "application/pdf"


def test_scoped_send_text_uses_bound_chat_only(app_env, monkeypatch) -> None:
    fake_client = FakeFeishuClient()
    monkeypatch.setattr(FeishuClient, "send_interactive_card", fake_client.send_interactive_card)
    client = TestClient(create_app())
    scope = _bind_default_chat("oc_bound")
    headers = {"X-SmartCore-Agent-Token": "agent-secret", "X-SmartCore-Agent-Scope": scope}

    resp = client.post(
        "/agent/feedback/send_text",
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
    card = {
        "schema": "2.0",
        "header": {"title": {"tag": "plain_text", "content": "提醒"}},
        "elements": [],
    }
    client = TestClient(create_app())
    scope = _bind_default_chat("oc_bound")
    headers = {"X-SmartCore-Agent-Token": "agent-secret", "X-SmartCore-Agent-Scope": scope}

    resp = client.post(
        "/agent/feedback/send_card",
        headers=headers,
        json={"chat_id": "oc_wrong", "card": card},
    )

    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert fake_client.card_calls[0][0] == "oc_bound"
    assert fake_client.card_calls[0][1]["header"]["title"]["content"] == "提醒"


def test_screen_push_uses_canonical_owner_scoped_route(app_env, monkeypatch) -> None:
    captured: dict = {}

    async def fake_broadcast(message: dict, *, userId: str | None = None) -> int:
        captured.update(message=message, userId=userId)
        return 1

    monkeypatch.setattr(
        "app.server.agent.routes.screenManager.broadcast",
        fake_broadcast,
    )
    client = TestClient(create_app())
    scope = _bind_default_chat("oc_bound")
    response = client.post(
        "/agent/feedback/screen_push",
        headers={
            "X-SmartCore-Agent-Token": "agent-secret",
            "X-SmartCore-Agent-Scope": scope,
        },
        json={"evtId": "evt-1", "title": "提醒", "content": "开始处理"},
    )

    assert response.status_code == 200
    assert response.json()["data"] == {"delivered": 1}
    assert captured == {
        "message": {
            "kind": "reminder",
            "evtId": "evt-1",
            "title": "提醒",
            "content": "开始处理",
        },
        "userId": "default",
    }


def test_agent_endpoints_return_ok_false_for_missing_ids(app_env) -> None:
    client = TestClient(create_app())
    scope = _bind_default_chat("oc_bound")
    headers = {"X-SmartCore-Agent-Token": "agent-secret", "X-SmartCore-Agent-Scope": scope}

    for path, payload in (
        ("/agent/db/update_event", {}),
        ("/agent/db/delete_event", {}),
        ("/agent/idea/to_event", {}),
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
        json={
            "evtType": "plan",
            "title": "只属于默认用户",
            "stTime": "2026-07-17T10:00:00+08:00",
            "userId": "other",
        },
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
    skill = (REPO_ROOT / "openclaw/skills/smartcore/SKILL.md").read_text(encoding="utf-8")
    assert "The Adapter owns Feishu delivery" in skill
    assert "--scope-file" in skill
    assert "Never construct HTTP requests" in skill
    assert "`--date YYYY-MM-DD`" in skill
    assert "`--start`" in skill
    assert "`data.items`" in skill
    assert "scripts/query_events.py" in skill
    assert "scripts/call_tool.py" in skill
    assert "native visual inputs" in skill
    assert "mediaImageOcr" not in skill
    assert "ocrEvidence" not in skill
    assert "commutePlanUpdate" in skill
    assert "Departure time and Plan start time are different" in skill
    assert "never call `evtCreate`" in skill
    assert "do not guess aliases" in skill
    assert "do not probe a fake `list` tool" in skill


def test_openclaw_adapter_prompt_owns_feishu_reply() -> None:
    adapter_source = (REPO_ROOT / "openclaw/adapter/adapter.py").read_text(encoding="utf-8")
    assert "X-SmartCore-Agent-Scope" in adapter_source
    assert "the Adapter owns final delivery" in adapter_source
    assert "/agent/feedback/send_text" in adapter_source
    assert "timeRange.start and timeRange.end" in adapter_source
    assert "data.items" in adapter_source
    assert "scripts/smartcore/scripts/query_events.py" not in adapter_source
    assert "skills/smartcore/scripts/query_events.py" in adapter_source
    assert "数据操作只执行两步" in adapter_source
    assert "禁止第二次调用 commutePlanUpdate" in adapter_source
    assert "OPENCLAW_MEDIA_MODEL" not in adapter_source
