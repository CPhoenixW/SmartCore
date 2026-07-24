from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from app.server.agent.scope import issue_agent_scope
from app.server.auth.security import create_session_token
from app.server.db.session import SessionLocal
from app.server.feishu.client import FeishuClient
from app.server.feishu.security import compute_signature
from app.server.main import create_app
from app.server.new_core.models import AppUser, FeishuBot
from app.server.new_core.notify import routeNotify
from app.server.new_core.preferences import update_user_preferences

pytestmark = pytest.mark.api


def _event(text: str, token: str) -> dict:
    return {
        "schema": "2.0",
        "header": {"event_type": "im.message.receive_v1", "token": token},
        "event": {
            "sender": {"sender_id": {"open_id": "ou_pair_user"}, "sender_type": "user"},
            "message": {
                "message_id": "om_pair_1",
                "chat_id": "oc_pair_chat",
                "chat_type": "p2p",
                "message_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
        },
    }


def _post_event(client: TestClient, event: dict, encrypt_key: str):
    body = json.dumps(event, separators=(",", ":"), ensure_ascii=False)
    timestamp = str(int(time.time()))
    nonce = "test-nonce"
    return client.post(
        "/feishu/event",
        content=body.encode("utf-8"),
        headers={
            "content-type": "application/json",
            "x-lark-request-timestamp": timestamp,
            "x-lark-request-nonce": nonce,
            "x-lark-signature": compute_signature(timestamp, nonce, encrypt_key, body),
        },
    )


def test_admin_can_pair_a_managed_feishu_bot_without_exposing_credentials(
    app_env, monkeypatch
) -> None:
    sent: list[tuple[str, str]] = []
    cards: list[str] = []
    monkeypatch.setattr(
        FeishuClient,
        "send_text",
        lambda self, chat, text, **kwargs: sent.append((chat, text)) or {"code": 0},
    )
    monkeypatch.setattr(
        FeishuClient,
        "send_interactive_card",
        lambda self, chat, card, **kwargs: cards.append(chat) or {"code": 0},
    )
    client = TestClient(create_app())
    db = SessionLocal()
    try:
        for row in db.query(FeishuBot).all():
            db.delete(row)
        db.commit()
    finally:
        db.close()
    assert (
        client.post(
            "/api/auth/setup", json={"password": "correct-horse-battery-staple"}
        ).status_code
        == 200
    )

    created = client.post(
        "/api/admin/feishuBots",
        json={
            "botName": "Personal bot",
            "appId": "cli_personal",
            "appSecret": "private-secret",
            "verificationToken": "personal-token",
            "encryptKey": "personal-key",
            "isDefault": True,
        },
    )
    assert created.status_code == 200
    bot = created.json()["data"]
    assert "private-secret" not in json.dumps(bot)
    assert "personal-token" not in json.dumps(bot)

    pair = client.post(f"/api/admin/feishuBots/{bot['botId']}/pair/start")
    assert pair.status_code == 200
    code = pair.json()["data"]["claimCode"]
    claimed = _post_event(client, _event(f"绑定 {code}", "personal-token"), "personal-key")
    assert claimed.status_code == 200
    assert sent and sent[-1][0] == "oc_pair_chat"
    assert all(text != "已收到，正在处理…" for _, text in sent)

    confirmed = client.post(
        f"/api/admin/feishuBots/{bot['botId']}/pair/{pair.json()['data']['pairId']}/confirm"
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["data"]["stat"] == "active"

    db = SessionLocal()
    try:
        update_user_preferences(db, reminder_channel="feishu")
        routed = routeNotify(
            db,
            title="Focus",
            content="Start now",
            screenOnline=False,
            evtId="evt_test",
            userId="default",
        )
    finally:
        db.close()
    assert routed == {"channel": "feishu", "stat": "sent"}
    assert cards == ["oc_pair_chat"]

    tested = client.post(f"/api/admin/feishuBots/{bot['botId']}/test")
    assert tested.status_code == 200
    assert tested.json()["data"]["hasRecipient"] is True


def test_feishu_pair_code_is_rejected_by_another_bot(app_env, monkeypatch) -> None:
    monkeypatch.setattr(FeishuClient, "send_text", lambda *args, **kwargs: {"code": 0})
    client = TestClient(create_app())
    db = SessionLocal()
    try:
        for row in db.query(FeishuBot).all():
            db.delete(row)
        db.commit()
    finally:
        db.close()
    assert (
        client.post(
            "/api/auth/setup", json={"password": "correct-horse-battery-staple"}
        ).status_code
        == 200
    )
    body = {"appId": "cli_bot", "appSecret": "secret", "encryptKey": "key"}
    first = client.post(
        "/api/admin/feishuBots",
        json={**body, "botName": "First", "verificationToken": "first-token"},
    )
    assert first.status_code == 200
    second = client.post(
        "/api/admin/feishuBots",
        json={**body, "botName": "Second", "verificationToken": "second-token"},
    )
    assert second.status_code == 409


def _message_event(text: str) -> dict:
    return {
        "schema": "2.0",
        "header": {
            "event_type": "im.message.receive_v1",
            "token": "verify-token",
        },
        "event": {
            "sender": {
                "sender_id": {"open_id": "ou_shared_user"},
                "sender_type": "user",
            },
            "message": {
                "message_id": "om_shared_pair",
                "chat_id": "oc_shared_chat",
                "chat_type": "p2p",
                "message_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
        },
    }


def _user_client(app, user_id: str) -> TestClient:
    client = TestClient(app)
    client.cookies.set("smartcore_session", create_session_token(user_id))
    return client


def test_normal_user_pairs_default_bot_and_uses_own_chat(app_env, monkeypatch) -> None:
    text_calls: list[tuple[str, str]] = []
    card_calls: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        FeishuClient,
        "send_text",
        lambda self, chat, text, **kwargs: text_calls.append((chat, text)) or {"code": 0},
    )
    monkeypatch.setattr(
        FeishuClient,
        "send_interactive_card",
        lambda self, chat, card, **kwargs: card_calls.append((chat, card)) or {"code": 0},
    )
    app = create_app()
    db = SessionLocal()
    try:
        db.add(
            AppUser(
                userId="normal",
                loginName="normal",
                displayName="Normal",
                role="user",
            )
        )
        db.commit()
        bot = db.query(FeishuBot).filter(FeishuBot.isDefault.is_(True)).one()
        bot_id = bot.botId
        original_default_chat = bot.defaultChatCipher
    finally:
        db.close()

    client = _user_client(app, "normal")
    started = client.post("/api/feishu/pair/start")
    assert started.status_code == 200
    pair = started.json()["data"]
    assert pair["botId"] == bot_id
    assert pair["deviceKind"] == "feishuBot"
    assert "appSecret" not in json.dumps(pair)

    claimed = client.post(
        "/feishu/event",
        json=_message_event(f"绑定 {pair['claimCode']}"),
    )
    assert claimed.status_code == 200
    assert claimed.json()["msg"] == "pairing claimed"
    assert text_calls[-1][0] == "oc_shared_chat"
    assert client.get(f"/api/feishu/pair/{pair['pairId']}").json()["data"]["stat"] == "claimed"

    confirmed = client.post(f"/api/feishu/pair/{pair['pairId']}/confirm")
    assert confirmed.status_code == 200
    bind_id = confirmed.json()["data"]["bindId"]
    bindings = client.get("/api/feishu/bindings").json()["data"]
    assert [row["bindId"] for row in bindings] == [bind_id]
    assert bindings[0]["chatHint"].endswith("_chat")

    db = SessionLocal()
    try:
        bot = db.get(FeishuBot, bot_id)
        assert bot is not None
        assert bot.defaultChatCipher == original_default_chat
        update_user_preferences(db, reminder_channel="feishu", user_id="normal")
        routed = routeNotify(
            db,
            title="Shared reminder",
            content="Only normal sees this",
            screenOnline=False,
            evtId="evt_shared",
            userId="normal",
        )
        start_routed = routeNotify(
            db,
            title="Starts soon",
            content="No task actions yet",
            screenOnline=False,
            evtId="evt_shared",
            phase="start",
            userId="normal",
        )
    finally:
        db.close()
    assert routed == {"channel": "feishu", "stat": "sent"}
    assert start_routed == {"channel": "feishu", "stat": "sent"}
    assert [chat for chat, _card in card_calls] == [
        "oc_shared_chat",
        "oc_shared_chat",
    ]
    assert card_calls[0][1]["elements"][-1]["tag"] == "action"
    assert all(element["tag"] != "action" for element in card_calls[1][1]["elements"])
    scope = issue_agent_scope(
        userId="normal",
        botId=bot_id,
        chatId="oc_shared_chat",
    )
    feedback = client.post(
        "/agent/feedback/send_text",
        headers={
            "X-SmartCore-Agent-Token": "agent-secret",
            "X-SmartCore-Agent-Scope": scope,
        },
        json={"text": "**完成**"},
    )
    assert feedback.status_code == 200
    assert feedback.json()["ok"] is True
    assert [chat for chat, _card in card_calls] == [
        "oc_shared_chat",
        "oc_shared_chat",
        "oc_shared_chat",
    ]


def test_user_feishu_pairing_is_owner_scoped(app_env, monkeypatch) -> None:
    monkeypatch.setattr(FeishuClient, "send_text", lambda *args, **kwargs: {"code": 0})
    app = create_app()
    db = SessionLocal()
    try:
        db.add_all(
            [
                AppUser(userId="owner", loginName="owner", displayName="Owner", role="user"),
                AppUser(
                    userId="intruder",
                    loginName="intruder",
                    displayName="Intruder",
                    role="user",
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    owner = _user_client(app, "owner")
    intruder = _user_client(app, "intruder")
    pair = owner.post("/api/feishu/pair/start").json()["data"]

    assert intruder.get(f"/api/feishu/pair/{pair['pairId']}").status_code == 404
    assert intruder.post(f"/api/feishu/pair/{pair['pairId']}/confirm").status_code == 409

    owner.post("/feishu/event", json=_message_event(f"绑定 {pair['claimCode']}"))
    bind_id = owner.post(f"/api/feishu/pair/{pair['pairId']}/confirm").json()["data"]["bindId"]
    assert intruder.delete(f"/api/feishu/bindings/{bind_id}").status_code == 404
    assert owner.delete(f"/api/feishu/bindings/{bind_id}").status_code == 200


def test_unbound_normal_user_does_not_fall_back_to_admin_chat(app_env, monkeypatch) -> None:
    sent: list[str] = []
    monkeypatch.setattr(
        FeishuClient,
        "send_text",
        lambda self, chat, text, **kwargs: sent.append(chat) or {"code": 0},
    )
    create_app()
    db = SessionLocal()
    try:
        db.add(
            AppUser(
                userId="unbound",
                loginName="unbound",
                displayName="Unbound",
                role="user",
            )
        )
        db.commit()
        update_user_preferences(db, reminder_channel="feishu", user_id="unbound")
        routed = routeNotify(
            db,
            title="Private",
            content="Do not leak",
            screenOnline=False,
            userId="unbound",
        )
    finally:
        db.close()
    assert routed == {"channel": "feishu", "stat": "failed"}
    assert sent == []
