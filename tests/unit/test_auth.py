from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.server.auth.security import (
    create_session_token,
    decode_session_token,
    hash_password,
    verify_password,
)
from app.server.db.session import Base
from app.server.new_core import crud
from app.server.new_core.models import AppUser  # noqa: F401

pytestmark = pytest.mark.unit


def test_password_hash_is_not_plaintext_and_verifies() -> None:
    encoded = hash_password("correct-horse-battery-staple")
    assert "correct-horse" not in encoded
    assert verify_password("correct-horse-battery-staple", encoded)
    assert not verify_password("wrong-password", encoded)


def test_signed_session_round_trip() -> None:
    token = create_session_token("default")
    assert decode_session_token(token) == "default"
    assert decode_session_token(f"{token}x") is None


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return Session(engine)


def test_user_table_contains_persisted_language_column() -> None:
    assert "language" in AppUser.__table__.columns
    assert AppUser.__table__.columns["language"].nullable is False


def test_language_state_round_trips_through_user_record() -> None:
    db = _session()
    try:
        assert crud.getCurrentUser(db)["language"] == "zh"
        updated = crud.updateCurrentUser(db, language="en")
        assert updated["language"] == "en"
        assert crud.getCurrentUser(db)["language"] == "en"
    finally:
        db.close()
