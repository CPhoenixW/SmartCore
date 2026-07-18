import json

from fastapi.testclient import TestClient

from app.agent.scope import issue_agent_scope
from app.auth.security import create_session_token
from app.db.session import SessionLocal
from app.feishu.client import FeishuClient
from app.main import create_app
from app.new_core.models import AppUser, FeishuBot
from app.new_core.notify import routeNotify
from app.new_core.preferences import update_user_preferences


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
    card_calls: list[str] = []
    monkeypatch.setattr(
        FeishuClient,
        "send_text",
        lambda self, chat, text, **kwargs: text_calls.append((chat, text)) or {"code": 0},
    )
    monkeypatch.setattr(
        FeishuClient,
        "send_interactive_card",
        lambda self, chat, card, **kwargs: card_calls.append(chat) or {"code": 0},
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
    finally:
        db.close()
    assert routed == {"channel": "feishu", "stat": "sent"}
    assert card_calls == ["oc_shared_chat"]

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
    assert card_calls == ["oc_shared_chat", "oc_shared_chat"]


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
    assert (
        intruder.post(f"/api/feishu/pair/{pair['pairId']}/confirm").status_code
        == 409
    )

    owner.post("/feishu/event", json=_message_event(f"绑定 {pair['claimCode']}"))
    bind_id = owner.post(
        f"/api/feishu/pair/{pair['pairId']}/confirm"
    ).json()["data"]["bindId"]
    assert intruder.delete(f"/api/feishu/bindings/{bind_id}").status_code == 404
    assert owner.delete(f"/api/feishu/bindings/{bind_id}").status_code == 200


def test_unbound_normal_user_does_not_fall_back_to_admin_chat(
    app_env, monkeypatch
) -> None:
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
