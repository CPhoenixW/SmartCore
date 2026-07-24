import os
import tempfile
from collections.abc import Callable
from contextlib import ExitStack
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# Application modules create the default FastAPI instance during import. Isolate
# that collection-time initialization from developer and production data.
_TEST_RUNTIME = tempfile.TemporaryDirectory(prefix="smartcore-pytest-")
_TEST_RUNTIME_PATH = Path(_TEST_RUNTIME.name)
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_RUNTIME_PATH / 'collection.sqlite'}"
os.environ["AUTH_SECRET_FILE"] = str(_TEST_RUNTIME_PATH / "auth_secret")
os.environ["SCHEDULER_ENABLED"] = "false"

from app.server.agent.scope import issue_agent_scope  # noqa: E402
from app.server.auth.security import create_session_token  # noqa: E402
from app.server.config import get_settings  # noqa: E402
from app.server.db.session import Base, reset_engine_for_tests  # noqa: E402
from app.server.feishu.client import FeishuClient  # noqa: E402
from app.server.main import create_app  # noqa: E402
from tests.factories import (  # noqa: E402
    FakeScheduler,
    create_user,
    feishu_message_event,
    pair_device,
)


@pytest.fixture
def app_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.sqlite"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("AGENT_API_TOKEN", "agent-secret")
    monkeypatch.setenv("DEVICE_API_TOKEN", "device-secret")
    monkeypatch.setenv("FEISHU_VERIFICATION_TOKEN", "verify-token")
    monkeypatch.setenv("FEISHU_APP_ID", "app-id")
    monkeypatch.setenv("FEISHU_APP_SECRET", "app-secret")
    monkeypatch.setenv("FEISHU_DEFAULT_CHAT_ID", "oc_default")
    get_settings.cache_clear()
    reset_engine_for_tests()
    try:
        yield db_path
    finally:
        get_settings.cache_clear()
        reset_engine_for_tests()


@pytest.fixture
def app_env(app_db):
    """Compatibility alias retained while test modules are consolidated."""
    return app_db


@pytest.fixture
def db_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def app(app_db):
    return create_app()


@pytest.fixture
def client(app) -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def signed_client_factory(app) -> Callable[[str], TestClient]:
    clients = ExitStack()

    def create(user_id: str) -> TestClient:
        test_client = clients.enter_context(TestClient(app))
        test_client.cookies.set("smartcore_session", create_session_token(user_id))
        return test_client

    yield create
    clients.close()


@pytest.fixture
def user_factory(db_session: Session):
    def create(**kwargs: Any):
        return create_user(db_session, **kwargs)

    return create


@pytest.fixture
def paired_device():
    return pair_device


@pytest.fixture
def managed_feishu_bot(client: TestClient):
    if client.post(
        "/api/auth/setup", json={"password": "correct-horse-battery-staple"}
    ).status_code not in {200, 409}:
        raise AssertionError("failed to initialize administrator")

    def create(**overrides: Any) -> dict[str, Any]:
        payload = {
            "botName": "Managed bot",
            "appId": "cli_test_app",
            "appSecret": "test-app-secret",
            "verificationToken": "test-verification-token",
            "encryptKey": "test-encrypt-key",
        }
        payload.update(overrides)
        response = client.post("/api/admin/feishuBots", json=payload)
        response.raise_for_status()
        return response.json()["data"]

    return create


@pytest.fixture
def agent_headers():
    def headers(user_id: str = "default", *, purpose: str = "web") -> dict[str, str]:
        return {
            "X-SmartCore-Agent-Token": "agent-secret",
            "X-SmartCore-Agent-Scope": issue_agent_scope(
                userId=user_id,
                purpose=purpose,
            ),
        }

    return headers


@pytest.fixture
def feishu_event_factory():
    return feishu_message_event


@pytest.fixture
def fake_feishu(monkeypatch):
    calls: dict[str, list[Any]] = {"text": [], "card": []}
    monkeypatch.setattr(
        FeishuClient,
        "send_text",
        lambda _self, chat, message, **_kwargs: (
            calls["text"].append((chat, message)) or {"code": 0}
        ),
    )
    monkeypatch.setattr(
        FeishuClient,
        "send_interactive_card",
        lambda _self, chat, card, **_kwargs: calls["card"].append((chat, card)) or {"code": 0},
    )
    return calls


@pytest.fixture
def openclaw_sink(monkeypatch):
    events: list[dict[str, Any]] = []

    class Response:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

    def post(_url: str, **kwargs: Any) -> Response:
        events.append(kwargs)
        return Response()

    monkeypatch.setattr("httpx.post", post)
    return events


@pytest.fixture
def fake_scheduler() -> FakeScheduler:
    return FakeScheduler()
