"""Tests for public access security features: disabled registration/setup, CSRF checks."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.api


@pytest.fixture
def public_access_client(monkeypatch):
    """Create a test client with public access mode enabled."""
    monkeypatch.setenv("PUBLIC_ACCESS_ENABLED", "true")
    monkeypatch.setenv("PUBLIC_ORIGIN", "https://phoenixw.online")
    monkeypatch.setenv("AUTH_REGISTRATION_ENABLED", "false")
    monkeypatch.setenv("AUTH_SETUP_ENABLED", "false")
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "true")
    from app.server.config import get_settings
    get_settings.cache_clear()
    from app.server.main import create_app
    client = TestClient(create_app())
    get_settings.cache_clear()
    return client


@pytest.fixture
def private_client(app_env):
    """Create a test client with private access mode (default)."""
    from app.server.main import create_app
    return TestClient(create_app())


class TestRegistrationDisabled:
    """Tests for disabled registration in public mode."""

    def test_registration_disabled_returns_403(self, public_access_client):
        response = public_access_client.post(
            "/api/auth/register",
            json={
                "loginName": "attacker",
                "password": "malicious-password123",
            },
            headers={"Origin": "https://phoenixw.online"},
        )
        assert response.status_code == 403
        assert "disabled" in response.json()["detail"].lower()

    def test_auth_status_reports_registration_disabled(self, public_access_client):
        response = public_access_client.get("/api/auth/status")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["registrationEnabled"] is False

    def test_registration_enabled_in_private_mode(self, private_client):
        response = private_client.post(
            "/api/auth/register",
            json={
                "loginName": "legitimate",
                "password": "correct-horse-battery",
            },
        )
        assert response.status_code == 200


class TestSetupDisabled:
    """Tests for disabled initial setup in public mode."""

    def test_setup_disabled_returns_403(self, public_access_client):
        response = public_access_client.post(
            "/api/auth/setup",
            json={"password": "attacker-password123"},
            headers={"Origin": "https://phoenixw.online"},
        )
        assert response.status_code == 403
        assert "disabled" in response.json()["detail"].lower()

    def test_auth_status_reports_setup_disabled(self, public_access_client):
        response = public_access_client.get("/api/auth/status")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["setupEnabled"] is False


class TestCsrfProtection:
    """Tests for CSRF/same-origin protection."""

    def test_post_without_origin_rejected_in_public_mode(self, public_access_client):
        response = public_access_client.post(
            "/api/auth/login",
            json={"userId": "test", "password": "test"},
        )
        assert response.status_code == 403
        assert "same-origin" in response.json()["detail"].lower()

    def test_post_with_wrong_origin_rejected(self, public_access_client):
        response = public_access_client.post(
            "/api/auth/login",
            json={"userId": "test", "password": "test"},
            headers={"Origin": "https://evil.com"},
        )
        assert response.status_code == 403

    def test_post_with_correct_origin_allowed(self, public_access_client):
        response = public_access_client.post(
            "/api/auth/login",
            json={"userId": "test", "password": "test"},
            headers={"Origin": "https://phoenixw.online"},
        )
        assert response.status_code == 401

    def test_get_request_allowed_without_origin(self, public_access_client):
        response = public_access_client.get("/api/auth/status")
        assert response.status_code == 200


class TestRateLimiting:
    """Tests for authentication rate limiting."""

    def test_login_rate_limited_after_10_attempts(self, private_client):
        for i in range(10):
            private_client.post(
                "/api/auth/login",
                json={"userId": f"user{i}", "password": "wrong"},
                headers={"Origin": "http://testserver"},
            )
        response = private_client.post(
            "/api/auth/login",
            json={"userId": "final", "password": "wrong"},
            headers={"Origin": "http://testserver"},
        )
        assert response.status_code == 429
        assert "Retry-After" in response.headers

    def test_registration_rate_limited(self, private_client):
        for i in range(10):
            private_client.post(
                "/api/auth/register",
                json={"loginName": f"user{i}", "password": "test12345678"},
                headers={"Origin": "http://testserver"},
            )
        response = private_client.post(
            "/api/auth/register",
            json={"loginName": "final", "password": "test12345678"},
            headers={"Origin": "http://testserver"},
        )
        assert response.status_code == 429


class TestConfigValidation:
    """Tests for public access configuration validation."""

    def test_public_access_requires_https_origin(self, monkeypatch):
        monkeypatch.setenv("PUBLIC_ACCESS_ENABLED", "true")
        monkeypatch.setenv("PUBLIC_ORIGIN", "http://insecure.example.com")
        monkeypatch.setenv("AUTH_REGISTRATION_ENABLED", "false")
        monkeypatch.setenv("AUTH_SETUP_ENABLED", "false")
        monkeypatch.setenv("AUTH_COOKIE_SECURE", "true")
        from app.server.config import Settings, get_settings
        get_settings.cache_clear()
        with pytest.raises(ValueError, match="HTTPS"):
            Settings()
        get_settings.cache_clear()

    def test_public_access_requires_secure_cookie(self, monkeypatch):
        monkeypatch.setenv("PUBLIC_ACCESS_ENABLED", "true")
        monkeypatch.setenv("PUBLIC_ORIGIN", "https://example.com")
        monkeypatch.setenv("AUTH_REGISTRATION_ENABLED", "false")
        monkeypatch.setenv("AUTH_SETUP_ENABLED", "false")
        monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
        from app.server.config import Settings, get_settings
        get_settings.cache_clear()
        with pytest.raises(ValueError, match="Secure cookies"):
            Settings()
        get_settings.cache_clear()

    def test_public_access_requires_disabled_registration(self, monkeypatch):
        monkeypatch.setenv("PUBLIC_ACCESS_ENABLED", "true")
        monkeypatch.setenv("PUBLIC_ORIGIN", "https://example.com")
        monkeypatch.setenv("AUTH_REGISTRATION_ENABLED", "true")
        monkeypatch.setenv("AUTH_SETUP_ENABLED", "false")
        monkeypatch.setenv("AUTH_COOKIE_SECURE", "true")
        from app.server.config import Settings, get_settings
        get_settings.cache_clear()
        with pytest.raises(ValueError, match="disabled registration"):
            Settings()
        get_settings.cache_clear()
