from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.server.db.session import Base
from app.server.new_core import crud
from app.server.new_core.models import AppUser  # noqa: F401


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
