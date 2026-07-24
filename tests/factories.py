from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.server.new_core import crud
from app.server.new_core.models import AppUser


def create_user(
    db: Session,
    *,
    user_id: str,
    login_name: str | None = None,
    role: str = "user",
    display_name: str | None = None,
) -> AppUser:
    row = AppUser(
        userId=user_id,
        loginName=login_name or user_id,
        displayName=display_name or user_id.title(),
        role=role,
    )
    db.add(row)
    db.commit()
    return row


def pair_device(
    client: TestClient,
    *,
    name: str = "Test device",
    kind: str = "screen",
) -> dict[str, Any]:
    pair = client.post(
        "/api/device/pair/start",
        json={"deviceName": name, "deviceKind": kind},
    ).json()["data"]
    client.post(
        f"/api/device/pair/{pair['pairId']}/claim",
        json={"claimCode": pair["claimCode"]},
    ).raise_for_status()
    client.post(f"/api/device/pair/{pair['pairId']}/confirm").raise_for_status()
    response = client.post(
        f"/api/device/pair/{pair['pairId']}/activate",
        json={"claimCode": pair["claimCode"]},
    )
    response.raise_for_status()
    return response.json()["data"]


def feishu_message_event(
    text: str,
    *,
    chat_id: str = "oc_test_chat",
    message_id: str = "om_test_message",
    open_id: str = "ou_test_user",
    token: str = "verify-token",
) -> dict[str, Any]:
    return {
        "schema": "2.0",
        "header": {"event_type": "im.message.receive_v1", "token": token},
        "event": {
            "sender": {
                "sender_id": {"open_id": open_id},
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


@dataclass
class FakeScheduler:
    jobs: list[tuple[Any, dict[str, Any]]] = field(default_factory=list)
    started: bool = False
    stopped: bool = False

    def add_job(self, function: Any, **kwargs: Any) -> None:
        self.jobs.append((function, kwargs))

    def start(self) -> None:
        self.started = True

    def shutdown(self, wait: bool = False) -> None:
        self.stopped = True


def ensure_default_user(db: Session) -> dict[str, Any]:
    user = crud.getCurrentUser(db)
    db.commit()
    return user
