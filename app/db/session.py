from collections.abc import Callable, Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None
_bound_database_url: str | None = None


def _ensure_engine() -> tuple[Engine, sessionmaker[Session]]:
    global _engine, _session_factory, _bound_database_url
    settings = get_settings()
    database_url = settings.database_url
    if _engine is not None and _bound_database_url == database_url:
        assert _session_factory is not None
        return _engine, _session_factory

    if _engine is not None:
        _engine.dispose()

    connect_args: dict[str, object] = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    _engine = create_engine(database_url, connect_args=connect_args)
    _session_factory = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    _bound_database_url = database_url
    return _engine, _session_factory


class _SessionLocalFactory:
    def __call__(self) -> Session:
        _, session_factory = _ensure_engine()
        return session_factory()


SessionLocal: Callable[[], Session] = _SessionLocalFactory()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_message_log_trace_columns() -> None:
    from sqlalchemy import inspect, text

    engine, _ = _ensure_engine()
    inspector = inspect(engine)
    if "message_logs" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("message_logs")}
    statements = []
    if "action_input" not in existing:
        statements.append("ALTER TABLE message_logs ADD COLUMN action_input JSON")
    if "db_result" not in existing:
        statements.append("ALTER TABLE message_logs ADD COLUMN db_result JSON")
    if not statements:
        return
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def _ensure_reminder_dedup_key_column() -> None:
    from sqlalchemy import inspect, text

    engine, _ = _ensure_engine()
    inspector = inspect(engine)
    if "reminders" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("reminders")}
    if "dedup_key" in existing:
        return
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE reminders ADD COLUMN dedup_key VARCHAR(200)"))


def init_db() -> None:
    from app.db import models  # noqa: F401

    settings = get_settings()
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    engine, _ = _ensure_engine()
    Base.metadata.create_all(bind=engine)
    _ensure_message_log_trace_columns()
    _ensure_reminder_dedup_key_column()
