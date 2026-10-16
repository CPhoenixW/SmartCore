"""Tests for browser origin checks and rate limiting in http_boundary.py."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi import Request

from app.server.auth.http_boundary import (
    RequestLimits,
    client_ip,
    machine_request,
    reject_request,
)
from app.server.config import Settings


class TestMachineRequest:
    """Tests for machine_request path classification."""

    def test_device_pair_paths_are_machine_requests(self):
        assert machine_request("/api/device/pair/abc123/claim", "POST")
        assert machine_request("/api/device/pair/abc123/activate", "POST")
        assert machine_request("/api/device/pair/abc123/status", "GET")

    def test_device_api_paths_are_machine_requests(self):
        assert machine_request("/api/device/dispatch", "GET")
        assert machine_request("/api/device/receipt", "POST")
        assert machine_request("/api/computer/activity/batch", "POST")
        assert machine_request("/api/computer/heartbeat", "POST")
        assert machine_request("/api/computer/codex-reports/batch", "POST")

    def test_post_dispatch_is_not_machine_request(self):
        assert not machine_request("/api/device/dispatch", "POST")

    def test_dev_paths_are_machine_requests(self):
        assert machine_request("/dev/heartbeat", "POST")
        assert machine_request("/dev/photo/request", "GET")
        assert machine_request("/dev/state", "POST")

    def test_screen_paths_are_machine_requests(self):
        assert machine_request("/screen/events", "GET")
        assert machine_request("/screen/ws", "GET")

    def test_screen_browser_paths_are_not_machine_requests(self):
        assert not machine_request("/screen/ws-ticket", "POST")
        assert not machine_request("/screen/reminder/action", "POST")

    def test_regular_api_paths_are_not_machine_requests(self):
        assert not machine_request("/api/auth/login", "POST")
        assert not machine_request("/api/evt", "GET")
        assert not machine_request("/api/idea", "POST")


class TestClientIp:
    """Tests for client_ip extraction with trusted proxies."""

    def _mock_request(self, peer_ip: str, forwarded_ip: str | None = None) -> MagicMock:
        request = MagicMock(spec=Request)
        request.client.host = peer_ip
        request.headers.get = MagicMock(return_value=forwarded_ip or peer_ip)
        return request

    def test_returns_peer_when_no_trusted_networks(self):
        request = self._mock_request("1.2.3.4")
        assert client_ip(request, "") == "1.2.3.4"

    def test_returns_peer_when_not_trusted(self):
        request = self._mock_request("1.2.3.4", "5.6.7.8")
        assert client_ip(request, "10.0.0.0/8") == "1.2.3.4"

    def test_returns_forwarded_when_trusted(self):
        request = self._mock_request("10.0.0.1", "5.6.7.8")
        request.headers.get = MagicMock(return_value="5.6.7.8")
        assert client_ip(request, "10.0.0.0/8") == "5.6.7.8"

    def test_handles_multiple_trusted_networks(self):
        request = self._mock_request("192.168.1.1", "8.8.8.8")
        request.headers.get = MagicMock(return_value="8.8.8.8")
        assert client_ip(request, "10.0.0.0/8, 192.168.0.0/16") == "8.8.8.8"


class TestRequestLimits:
    """Tests for rate limiting behavior."""

    def test_allows_requests_under_limit(self):
        limits = RequestLimits(capacity=100)
        for _ in range(5):
            assert limits.allow("test", "user1", 10, 60)

    def test_blocks_requests_over_limit(self):
        limits = RequestLimits(capacity=100)
        for _ in range(10):
            limits.allow("test", "user1", 10, 60)
        assert not limits.allow("test", "user1", 10, 60)

    def test_different_identities_have_separate_limits(self):
        limits = RequestLimits(capacity=100)
        for _ in range(10):
            limits.allow("test", "user1", 10, 60)
        assert limits.allow("test", "user2", 10, 60)

    def test_different_groups_have_separate_limits(self):
        limits = RequestLimits(capacity=100)
        for _ in range(10):
            limits.allow("auth", "user1", 10, 60)
        assert limits.allow("pairing", "user1", 10, 60)

    def test_capacity_limit_blocks_new_identities(self):
        limits = RequestLimits(capacity=2)
        limits.allow("test", "user1", 10, 60)
        limits.allow("test", "user2", 10, 60)
        assert not limits.allow("test", "user3", 10, 60)

    def test_expired_entries_are_cleaned(self):
        limits = RequestLimits(capacity=100)
        with patch("app.server.auth.http_boundary.time.monotonic") as mock_time:
            mock_time.return_value = 0.0
            for _ in range(10):
                limits.allow("test", "user1", 10, 60)
            mock_time.return_value = 61.0
            assert limits.allow("test", "user1", 10, 60)


class TestRejectRequest:
    """Tests for CSRF origin checking and rate limiting integration."""

    def _mock_request(
        self,
        path: str,
        method: str,
        origin: str | None = None,
        base_url: str = "http://localhost:8000/",
        peer_ip: str = "127.0.0.1",
    ) -> MagicMock:
        request = MagicMock(spec=Request)
        request.url.path = path
        request.method = method
        request.headers.get = MagicMock(return_value=origin)
        request.base_url = MagicMock()
        request.base_url.__str__ = MagicMock(return_value=base_url)
        request.client.host = peer_ip
        return request

    def _settings(self, public: bool = False, origin: str = "") -> Settings:
        return Settings(
            public_access_enabled=public,
            public_origin=origin,
            trusted_proxy_networks="",
            auth_cookie_secure=public,
            auth_registration_enabled=not public,
            auth_setup_enabled=not public,
        )

    def test_allows_get_requests_without_origin_check(self):
        request = self._mock_request("/api/auth/status", "GET")
        settings = self._settings()
        limits = RequestLimits()
        assert reject_request(request, settings, limits) is None

    def test_allows_matching_origin_in_private_mode(self):
        request = self._mock_request("/api/auth/login", "POST", origin="http://localhost:8000")
        settings = self._settings()
        limits = RequestLimits()
        assert reject_request(request, settings, limits) is None

    def test_rejects_mismatched_origin_in_private_mode(self):
        request = self._mock_request("/api/auth/login", "POST", origin="http://evil.com")
        settings = self._settings()
        limits = RequestLimits()
        response = reject_request(request, settings, limits)
        assert response is not None
        assert response.status_code == 403

    def test_allows_matching_origin_in_public_mode(self):
        request = self._mock_request("/api/auth/login", "POST", origin="https://example.com")
        settings = self._settings(public=True, origin="https://example.com")
        limits = RequestLimits()
        assert reject_request(request, settings, limits) is None

    def test_rejects_missing_origin_in_public_mode(self):
        request = self._mock_request("/api/auth/login", "POST", origin=None)
        settings = self._settings(public=True, origin="https://example.com")
        limits = RequestLimits()
        response = reject_request(request, settings, limits)
        assert response is not None
        assert response.status_code == 403

    def test_allows_missing_origin_for_machine_requests(self):
        request = self._mock_request("/dev/heartbeat", "POST", origin=None)
        settings = self._settings(public=True, origin="https://example.com")
        limits = RequestLimits()
        assert reject_request(request, settings, limits) is None

    def test_rate_limits_authentication_routes(self):
        settings = self._settings()
        limits = RequestLimits()
        for _ in range(10):
            request = self._mock_request("/api/auth/login", "POST", origin="http://localhost:8000")
            reject_request(request, settings, limits)
        request = self._mock_request("/api/auth/login", "POST", origin="http://localhost:8000")
        response = reject_request(request, settings, limits)
        assert response is not None
        assert response.status_code == 429

    def test_rate_limits_pairing_routes(self):
        settings = self._settings()
        limits = RequestLimits()
        for _ in range(120):
            request = self._mock_request("/api/device/pair/abc/claim", "POST", origin=None)
            reject_request(request, settings, limits)
        request = self._mock_request("/api/device/pair/abc/claim", "POST", origin=None)
        response = reject_request(request, settings, limits)
        assert response is not None
        assert response.status_code == 429

    def test_rate_limits_screen_ticket_route(self):
        settings = self._settings()
        limits = RequestLimits()
        for _ in range(30):
            request = self._mock_request("/screen/ws-ticket", "POST", origin="http://localhost:8000")
            reject_request(request, settings, limits)
        request = self._mock_request("/screen/ws-ticket", "POST", origin="http://localhost:8000")
        response = reject_request(request, settings, limits)
        assert response is not None
        assert response.status_code == 429

    def test_rate_limits_screen_reminder_action_route(self):
        settings = self._settings()
        limits = RequestLimits()
        for _ in range(60):
            request = self._mock_request("/screen/reminder/action", "POST", origin="http://localhost:8000")
            reject_request(request, settings, limits)
        request = self._mock_request("/screen/reminder/action", "POST", origin="http://localhost:8000")
        response = reject_request(request, settings, limits)
        assert response is not None
        assert response.status_code == 429

    def test_screen_browser_paths_require_csrf_in_public_mode(self):
        settings = self._settings(public=True, origin="https://example.com")
        limits = RequestLimits()
        request = self._mock_request("/screen/ws-ticket", "POST", origin=None)
        response = reject_request(request, settings, limits)
        assert response is not None
        assert response.status_code == 403

    def test_screen_browser_paths_allow_correct_origin(self):
        settings = self._settings(public=True, origin="https://example.com")
        limits = RequestLimits()
        request = self._mock_request("/screen/ws-ticket", "POST", origin="https://example.com")
        response = reject_request(request, settings, limits)
        assert response is None
