from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db import models  # noqa: F401
from app.db.session import Base
from app.operations.parser import ParsedOperation


def make_create_event(
    *,
    event_type: str,
    title: str,
    start_at: str | None = None,
    end_at: str | None = None,
    raw_text: str | None = None,
    source: str = "feishu",
    confidence: float = 0.9,
) -> ParsedOperation:
    event: dict[str, Any] = {"event_type": event_type, "title": title}
    if start_at is not None:
        event["start_at"] = start_at
    if end_at is not None:
        event["end_at"] = end_at
    text = raw_text or title
    payload = {
        "action": "create_event",
        "source": source,
        "raw_text": text,
        "payload": {"event": event},
    }
    return ParsedOperation(
        source=source,
        raw_text=text,
        action_name="create_event",
        payload=payload,
        confidence=confidence,
        needs_confirmation=True,
    )


def make_update_event(
    *,
    event_type: str,
    resource_id: int,
    patch: dict[str, Any],
    raw_text: str = "修改事项",
    source: str = "feishu",
    confidence: float = 0.9,
) -> ParsedOperation:
    payload = {
        "action": "update_event",
        "source": source,
        "raw_text": raw_text,
        "payload": {
            "selector": {"event_type": event_type, "id": resource_id},
            "patch": patch,
        },
    }
    return ParsedOperation(
        source=source,
        raw_text=raw_text,
        action_name="update_event",
        payload=payload,
        confidence=confidence,
        needs_confirmation=True,
    )


def make_delete_event(
    *,
    event_type: str,
    resource_id: int | None = None,
    targets: list[dict[str, Any]] | None = None,
    raw_text: str = "删除事项",
    source: str = "feishu",
    confidence: float = 0.9,
) -> ParsedOperation:
    selector: dict[str, Any] = {"event_type": event_type}
    if targets is not None:
        selector["targets"] = targets
    elif resource_id is not None:
        selector["id"] = resource_id
    payload = {
        "action": "delete_event",
        "source": source,
        "raw_text": raw_text,
        "payload": {"selector": selector},
    }
    return ParsedOperation(
        source=source,
        raw_text=raw_text,
        action_name="delete_event",
        payload=payload,
        confidence=confidence,
        needs_confirmation=True,
    )


@pytest.fixture
def db_session(tmp_path, monkeypatch) -> Generator[Session, None, None]:
    db_path = tmp_path / "test.sqlite"
    database_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()

    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
        get_settings.cache_clear()
