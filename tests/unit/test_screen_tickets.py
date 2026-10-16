"""Tests for screen WebSocket ticket system in tickets.py."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.server.screen.tickets import ScreenTickets


class TestScreenTickets:
    """Tests for short-lived, single-use WebSocket tickets."""

    def test_issue_returns_ticket(self):
        tickets = ScreenTickets()
        ticket = tickets.issue("device1", "hash123")
        assert isinstance(ticket, str)
        assert len(ticket) > 20

    def test_consume_returns_token_hash(self):
        tickets = ScreenTickets()
        ticket = tickets.issue("device1", "hash123")
        token_hash = tickets.consume(ticket, "device1")
        assert token_hash == "hash123"

    def test_ticket_is_single_use(self):
        tickets = ScreenTickets()
        ticket = tickets.issue("device1", "hash123")
        tickets.consume(ticket, "device1")
        with pytest.raises(HTTPException) as exc:
            tickets.consume(ticket, "device1")
        assert exc.value.status_code == 401

    def test_ticket_requires_matching_device(self):
        tickets = ScreenTickets()
        ticket = tickets.issue("device1", "hash123")
        with pytest.raises(HTTPException) as exc:
            tickets.consume(ticket, "device2")
        assert exc.value.status_code == 401

    def test_ticket_expires_after_60_seconds(self):
        tickets = ScreenTickets()
        with patch("app.server.screen.tickets.time.monotonic") as mock_time:
            mock_time.return_value = 0.0
            ticket = tickets.issue("device1", "hash123")
            mock_time.return_value = 61.0
            with pytest.raises(HTTPException) as exc:
                tickets.consume(ticket, "device1")
            assert exc.value.status_code == 401

    def test_invalid_ticket_rejected(self):
        tickets = ScreenTickets()
        tickets.issue("device1", "hash123")
        with pytest.raises(HTTPException) as exc:
            tickets.consume("invalid_ticket", "device1")
        assert exc.value.status_code == 401

    def test_capacity_limit_raises_429(self):
        tickets = ScreenTickets()
        tickets._tickets = {f"hash{i}": (float("inf"), f"device{i}", f"tokenhash{i}") for i in range(4096)}
        with pytest.raises(HTTPException) as exc:
            tickets.issue("new_device", "new_hash")
        assert exc.value.status_code == 429

    def test_expired_tickets_cleaned_on_issue(self):
        tickets = ScreenTickets()
        with patch("app.server.screen.tickets.time.monotonic") as mock_time:
            mock_time.return_value = 0.0
            tickets.issue("device1", "hash1")
            tickets.issue("device2", "hash2")
            assert len(tickets._tickets) == 2
            mock_time.return_value = 61.0
            tickets.issue("device3", "hash3")
            assert len(tickets._tickets) == 1
