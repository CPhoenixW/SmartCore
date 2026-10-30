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


def test_work_pwa_assets_are_public_but_pages_remain_protected(tmp_path: Path) -> None:
    frontend_dist = tmp_path / "dist"
    (frontend_dist / "assets").mkdir(parents=True)
    (frontend_dist / "index.html").write_text("<html></html>", encoding="utf-8")
    (frontend_dist / "favicon.png").write_bytes(b"favicon")
    (frontend_dist / "icon-192.png").write_bytes(b"icon-192")
    (frontend_dist / "icon-512.png").write_bytes(b"icon-512")
    (frontend_dist / "manifest.webmanifest").write_text("{}", encoding="utf-8")
    (frontend_dist / "sw.js").write_text("self.skipWaiting()", encoding="utf-8")
    app = FastAPI()
    _register_work_frontend(app, frontend_dist)

    with TestClient(app) as test_client:
        assets = {
            path: test_client.get(f"/work/{path}", follow_redirects=False)
            for path in (
                "favicon.png",
                "icon-192.png",
                "icon-512.png",
                "manifest.webmanifest",
                "sw.js",
            )
        }
        protected_page = test_client.get("/work/ideas", follow_redirects=False)

    assert all(response.status_code == 200 for response in assets.values())
    assert assets["favicon.png"].headers["content-type"].startswith("image/png")
    assert assets["icon-192.png"].content == b"icon-192"
    assert assets["icon-512.png"].content == b"icon-512"
    assert assets["manifest.webmanifest"].headers["content-type"].startswith(
        "application/manifest+json"
    )
    assert assets["sw.js"].headers["content-type"].startswith("application/javascript")
    assert assets["sw.js"].headers["cache-control"] == "no-cache"
    assert protected_page.status_code == 303
    assert protected_page.headers["location"] == "/work/login?next=/work/ideas"
