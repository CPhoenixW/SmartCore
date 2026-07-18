import json
import time

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.feishu.client import FeishuClient
from app.feishu.security import compute_signature
from app.main import create_app
from app.new_core.models import FeishuBot
from app.new_core.notify import routeNotify
from app.new_core.preferences import update_user_preferences


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


def test_admin_can_pair_a_managed_feishu_bot_without_exposing_credentials(app_env, monkeypatch) -> None:
    sent: list[tuple[str, str]] = []
    cards: list[str] = []
    monkeypatch.setattr(FeishuClient, "send_text", lambda self, chat, text, **kwargs: sent.append((chat, text)) or {"code": 0})
    monkeypatch.setattr(FeishuClient, "send_interactive_card", lambda self, chat, card, **kwargs: cards.append(chat) or {"code": 0})
    client = TestClient(create_app())
    db = SessionLocal()
    try:
        for row in db.query(FeishuBot).all():
            db.delete(row)
        db.commit()
    finally:
        db.close()
    assert client.post("/api/auth/setup", json={"password": "correct-horse-battery-staple"}).status_code == 200

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

    confirmed = client.post(f"/api/admin/feishuBots/{bot['botId']}/pair/{pair.json()['data']['pairId']}/confirm")
    assert confirmed.status_code == 200
    assert confirmed.json()["data"]["stat"] == "active"

    db = SessionLocal()
    try:
        update_user_preferences(db, reminder_channel="feishu")
        routed = routeNotify(db, title="Focus", content="Start now", screenOnline=False, evtId="evt_test", userId="default")
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
    assert client.post("/api/auth/setup", json={"password": "correct-horse-battery-staple"}).status_code == 200
    body = {"appId": "cli_bot", "appSecret": "secret", "encryptKey": "key"}
    first = client.post("/api/admin/feishuBots", json={**body, "botName": "First", "verificationToken": "first-token"})
    assert first.status_code == 200
    second = client.post("/api/admin/feishuBots", json={**body, "botName": "Second", "verificationToken": "second-token"})
    assert second.status_code == 409
