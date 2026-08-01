from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.server.auth.security import session_token_hash
from app.server.db.session import SessionLocal
from app.server.main import create_app
from app.server.new_core.models import UserSession

pytestmark = pytest.mark.api


def _setup_client() -> TestClient:
    client = TestClient(create_app())
    assert (
        client.post(
            "/api/auth/setup", json={"password": "correct-horse-battery-staple"}
        ).status_code
        == 200
    )
    return client


def _paired_device(client: TestClient, kind: str) -> dict:
    pair = client.post(
        "/api/device/pair/start", json={"deviceName": kind, "deviceKind": kind}
    ).json()["data"]
    assert (
        client.post(
            f"/api/device/pair/{pair['pairId']}/claim", json={"claimCode": pair["claimCode"]}
        ).status_code
        == 200
    )
    assert client.post(f"/api/device/pair/{pair['pairId']}/confirm").status_code == 200
    return client.post(
        f"/api/device/pair/{pair['pairId']}/activate", json={"claimCode": pair["claimCode"]}
    ).json()["data"]


def test_register_creates_unprivileged_session(app_env) -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/auth/register",
        json={
            "loginName": "phoenix",
            "displayName": "Phoenix",
            "password": "correct-horse-battery-staple",
        },
    )
    assert response.status_code == 200
    assert response.json()["data"]["role"] == "user"
    assert client.get("/api/auth/me").json()["data"]["loginName"] == "phoenix"
    assert (
        client.post(
            "/api/auth/register",
            json={"loginName": "phoenix", "password": "correct-horse-battery-staple"},
        ).status_code
        == 409
    )


def test_login_name_session_uses_internal_user_id(app_env) -> None:
    client = TestClient(create_app())
    registered = client.post(
        "/api/auth/register",
        json={
            "loginName": "phoenix",
            "displayName": "Phoenix",
            "password": "correct-horse-battery-staple",
        },
    ).json()["data"]
    assert client.post("/api/auth/logout").status_code == 200

    logged_in = client.post(
        "/api/auth/login",
        json={"userId": "phoenix", "password": "correct-horse-battery-staple"},
    )
    assert logged_in.status_code == 200
    assert logged_in.json()["data"]["userId"] == registered["userId"]
    assert client.get("/api/auth/me").json()["data"]["userId"] == registered["userId"]

    profile = client.get("/api/user/me")
    assert profile.status_code == 200
    assert profile.json()["data"]["userId"] == registered["userId"]
    assert profile.json()["data"]["displayName"] == "Phoenix"

    event = client.post(
        "/api/planEvt",
        json={
            "title": "Normal user event",
            "stTime": "2026-07-18T10:00:00+08:00",
            "durationMin": 60,
        },
    )
    assert event.status_code == 200
    assert event.json()["data"]["userId"] == registered["userId"]

    assert client.post("/api/auth/logout").status_code == 200
    internal_id_login = client.post(
        "/api/auth/login",
        json={"userId": registered["userId"], "password": "correct-horse-battery-staple"},
    )
    assert internal_id_login.status_code == 200
    assert client.get("/api/user/me").json()["data"]["displayName"] == "Phoenix"


def test_server_sessions_can_be_listed_revoked_and_invalidated_by_password_change(app_env) -> None:
    first = TestClient(create_app())
    registered = first.post(
        "/api/auth/register",
        json={
            "loginName": "session-user",
            "password": "correct-horse-battery-staple",
        },
    )
    assert registered.status_code == 200
    old_first_token = first.cookies.get("smartcore_session")
    assert old_first_token

    db = SessionLocal()
    try:
        stored = db.query(UserSession).filter_by(tokenHash=session_token_hash(old_first_token)).one()
        assert stored.tokenHash != old_first_token
        assert old_first_token not in " ".join(str(value) for value in vars(stored).values())
    finally:
        db.close()

    second = TestClient(create_app())
    assert second.post(
        "/api/auth/login",
        json={"userId": "session-user", "password": "correct-horse-battery-staple"},
    ).status_code == 200
    second_token = second.cookies.get("smartcore_session")

    sessions = first.get("/api/auth/sessions")
    assert sessions.status_code == 200
    rows = sessions.json()["data"]
    assert len(rows) == 2
    second_row = next(row for row in rows if row["current"] is False)
    assert first.delete(f"/api/auth/sessions/{second_row['sessionId']}").status_code == 200
    assert second.get("/api/auth/me").status_code == 401

    changed = first.post(
        "/api/auth/password",
        json={
            "currentPassword": "correct-horse-battery-staple",
            "newPassword": "updated-horse-battery-staple",
        },
    )
    assert changed.status_code == 200
    assert first.cookies.get("smartcore_session") != old_first_token
    assert first.get("/api/auth/me").status_code == 200

    stale = TestClient(create_app())
    stale.cookies.set("smartcore_session", old_first_token)
    assert stale.get("/api/auth/me").status_code == 401
    stale.cookies.set("smartcore_session", second_token)
    assert stale.get("/api/auth/me").status_code == 401
    assert first.post("/api/auth/logout-all").status_code == 200
    assert first.get("/api/auth/me").status_code == 401


def test_session_revocation_and_logout_all_are_actor_scoped(app_env) -> None:
    owner = TestClient(create_app())
    owner_user = owner.post(
        "/api/auth/register",
        json={"loginName": "session-owner", "password": "correct-horse-battery-staple"},
    ).json()["data"]

    other = TestClient(create_app())
    other_user = other.post(
        "/api/auth/register",
        json={"loginName": "session-other", "password": "correct-horse-battery-staple"},
    ).json()["data"]
    other_session = other.get("/api/auth/sessions").json()["data"][0]

    assert owner.delete(f"/api/auth/sessions/{other_session['sessionId']}").status_code == 404
    assert other.get("/api/auth/me").json()["data"]["userId"] == other_user["userId"]

    assert owner.post("/api/auth/logout-all").status_code == 200
    assert owner.get("/api/auth/me").status_code == 401
    assert other.get("/api/auth/me").json()["data"]["userId"] == other_user["userId"]
    assert owner_user["userId"] != other_user["userId"]


def test_admin_active_user_switch_cannot_change_selected_users_password(app_env) -> None:
    admin = _setup_client()
    created = admin.post(
        "/api/auth/register",
        json={"loginName": "selected-user", "password": "correct-horse-battery-staple"},
    )
    assert created.status_code == 200
    selected_user_id = created.json()["data"]["userId"]

    assert admin.post("/api/auth/logout").status_code == 200
    assert admin.post(
        "/api/auth/login",
        json={"userId": "default", "password": "correct-horse-battery-staple"},
    ).status_code == 200
    assert admin.post(
        "/api/admin/activeUser", json={"userId": selected_user_id}
    ).status_code == 200

    response = admin.post(
        "/api/auth/password",
        json={
            "currentPassword": "correct-horse-battery-staple",
            "newPassword": "updated-horse-battery-staple",
        },
    )
    assert response.status_code == 409

    selected = TestClient(create_app())
    assert selected.post(
        "/api/auth/login",
        json={"userId": "selected-user", "password": "correct-horse-battery-staple"},
    ).status_code == 200


def test_paired_device_token_can_poll_photo_requests(app_env) -> None:
    client = _setup_client()
    activated = _paired_device(client, "pi")
    device_id = activated["device"]["deviceId"]
    token = activated["deviceToken"]
    assert (
        client.post(f"/api/device/{device_id}/photoRequest", json={"reason": "test"}).status_code
        == 200
    )
    assert (
        client.get(
            f"/dev/photo/request?devId={device_id}", headers={"X-SmartCore-Device-Token": token}
        ).status_code
        == 200
    )
    assert client.get(f"/dev/photo/request?devId={device_id}").status_code == 401


def test_pi_photo_web_routes_are_owner_scoped(app_env) -> None:
    owner = _setup_client()
    activated = _paired_device(owner, "pi")
    device_id = activated["device"]["deviceId"]
    created = owner.post(f"/api/device/{device_id}/photoRequest", json={"reason": "owner"})
    assert created.status_code == 200
    request_id = created.json()["data"]["requestId"]

    anonymous = TestClient(create_app())
    assert anonymous.post(f"/api/device/{device_id}/photoRequest", json={}).status_code == 401
    assert anonymous.get(f"/api/device/photoRequest/{request_id}").status_code == 401
    assert anonymous.get(f"/api/device/photoRequest/{request_id}/image").status_code == 401

    other = TestClient(create_app())
    assert other.post(
        "/api/auth/register",
        json={"loginName": "photo-other", "password": "correct-horse-battery-staple"},
    ).status_code == 200
    assert other.post(f"/api/device/{device_id}/photoRequest", json={}).status_code == 404
    assert other.get(f"/api/device/{device_id}/photoRequests").status_code == 404
    assert other.get(f"/api/device/photoRequest/{request_id}").status_code == 404
    assert other.get(f"/api/device/photoRequest/{request_id}/image").status_code == 404


def test_screen_websocket_requires_its_device_credential(app_env) -> None:
    client = _setup_client()
    activated = _paired_device(client, "screen")
    device_id = activated["device"]["deviceId"]
    token = activated["deviceToken"]
    with client.websocket_connect(
        f"/screen/ws?deviceId={device_id}&deviceToken={token}"
    ) as websocket:
        assert websocket.receive_json()["kind"] == "state"
    assert (
        client.get(
            "/screen/events",
            params={"deviceId": device_id},
            headers={"X-SmartCore-Device-Token": token},
        ).status_code
        == 200
    )
    assert client.get("/screen/events", params={"deviceId": device_id}).status_code == 401


def test_deleted_device_token_is_revoked(app_env) -> None:
    client = _setup_client()
    activated = _paired_device(client, "screen")
    device_id = activated["device"]["deviceId"]
    token = activated["deviceToken"]
    assert client.delete(f"/api/device/{device_id}").status_code == 200
    assert (
        client.get(
            "/screen/events",
            params={"deviceId": device_id},
            headers={"X-SmartCore-Device-Token": token},
        ).status_code
        == 401
    )


def test_feishu_binding_claims_then_confirms_chat(app_env, monkeypatch) -> None:
    client = _setup_client()
    bot = client.get("/api/admin/feishuBots").json()["data"][0]
    pair = client.post(f"/api/admin/feishuBots/{bot['botId']}/pair/start").json()["data"]
    monkeypatch.setenv("OPENCLAW_EVENTS_ENDPOINT", "http://openclaw.local/events")
    event = {
        "schema": "2.0",
        "header": {"event_type": "im.message.receive_v1", "token": "verify-token"},
        "event": {
            "sender": {"sender_id": {"open_id": "ou_bound"}, "sender_type": "user"},
            "message": {
                "message_id": "om_bind",
                "chat_id": "oc_bind",
                "chat_type": "p2p",
                "message_type": "text",
                "content": json.dumps({"text": f"绑定 {pair['claimCode']}"}),
            },
        },
    }
    assert client.post("/feishu/event", json=event).status_code == 200
    confirmed = client.post(f"/api/admin/feishuBots/{bot['botId']}/pair/{pair['pairId']}/confirm")
    assert confirmed.status_code == 200
    assert confirmed.json()["data"]["stat"] == "active"


def test_same_feishu_identity_can_bind_two_chats_for_the_same_user(app_env, monkeypatch) -> None:
    client = _setup_client()
    bot = client.get("/api/admin/feishuBots").json()["data"][0]
    monkeypatch.setattr(
        "app.server.feishu.client.FeishuClient.send_text", lambda *_args, **_kwargs: {"code": 0}
    )

    for index, chat_id in enumerate(("oc_first", "oc_second"), start=1):
        pair = client.post(f"/api/admin/feishuBots/{bot['botId']}/pair/start").json()["data"]
        event = {
            "schema": "2.0",
            "header": {"event_type": "im.message.receive_v1", "token": "verify-token"},
            "event": {
                "sender": {"sender_id": {"open_id": "ou_same"}, "sender_type": "user"},
                "message": {
                    "message_id": f"om_bind_{index}",
                    "chat_id": chat_id,
                    "chat_type": "p2p",
                    "message_type": "text",
                    "content": json.dumps({"text": f"绑定 {pair['claimCode']}"}),
                },
            },
        }
        assert client.post("/feishu/event", json=event).status_code == 200
        assert (
            client.post(
                f"/api/admin/feishuBots/{bot['botId']}/pair/{pair['pairId']}/confirm"
            ).status_code
            == 200
        )
