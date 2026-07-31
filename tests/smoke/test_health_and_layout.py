from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.server.config import PROJECT_ROOT, Settings
from app.server.main import _register_work_frontend

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


def test_work_favicon_is_public_but_pages_remain_protected(tmp_path: Path) -> None:
    frontend_dist = tmp_path / "dist"
    (frontend_dist / "assets").mkdir(parents=True)
    (frontend_dist / "index.html").write_text("<html></html>", encoding="utf-8")
    (frontend_dist / "favicon.png").write_bytes(b"favicon")
    app = FastAPI()
    _register_work_frontend(app, frontend_dist)

    with TestClient(app) as test_client:
        favicon = test_client.get("/work/favicon.png", follow_redirects=False)
        protected_page = test_client.get("/work/ideas", follow_redirects=False)

    assert favicon.status_code == 200
    assert favicon.headers["content-type"].startswith("image/png")
    assert favicon.content == b"favicon"
    assert protected_page.status_code == 303
    assert protected_page.headers["location"] == "/work/login?next=/work/ideas"
