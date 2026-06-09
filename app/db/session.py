from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _create_engine():
    settings = get_settings()
    connect_args = {}
    if settings.database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(settings.database_url, connect_args=connect_args)


engine = _create_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_message_log_trace_columns() -> None:
    from sqlalchemy import inspect, text

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
    Base.metadata.create_all(bind=engine)
    _ensure_message_log_trace_columns()
    _ensure_reminder_dedup_key_column()
