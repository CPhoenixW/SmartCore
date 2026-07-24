import os
import tempfile
from pathlib import Path

import pytest

# Application modules create the default FastAPI instance during import. Isolate
# that collection-time initialization from developer and production data.
_TEST_RUNTIME = tempfile.TemporaryDirectory(prefix="smartcore-pytest-")
_TEST_RUNTIME_PATH = Path(_TEST_RUNTIME.name)
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_RUNTIME_PATH / 'collection.sqlite'}"
os.environ["AUTH_SECRET_FILE"] = str(_TEST_RUNTIME_PATH / "auth_secret")
os.environ["SCHEDULER_ENABLED"] = "false"

from app.server.config import get_settings  # noqa: E402
from app.server.db.session import reset_engine_for_tests  # noqa: E402


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
