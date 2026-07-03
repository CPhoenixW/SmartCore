import pytest

from app.config import get_settings
from app.db.session import reset_engine_for_tests


@pytest.fixture
def app_env(tmp_path, monkeypatch):
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
