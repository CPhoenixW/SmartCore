from __future__ import annotations

from pathlib import Path

import pytest

from app.server.config import PROJECT_ROOT, Settings

pytestmark = pytest.mark.smoke


def test_healthz_returns_ok(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_server_defaults_resolve_from_repository_root() -> None:
    expected_root = Path(__file__).resolve().parents[2]
    assert PROJECT_ROOT == expected_root
    assert Settings.model_fields["database_url"].default == (
        f"sqlite:///{expected_root / 'data' / 'smartcore.sqlite'}"
    )
    assert Settings.model_fields["idea_media_dir"].default == str(
        expected_root / "data" / "idea_media"
    )
