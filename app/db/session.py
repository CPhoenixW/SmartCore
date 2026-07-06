from collections.abc import Callable, Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings
from app.db.schema_paths import schemaSqlPath


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


def dispose_engine() -> None:
    global _engine, _session_factory, _bound_database_url
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
    _bound_database_url = None


def reset_engine_for_tests() -> None:
    dispose_engine()


def _execute_sqlite_script(db_path: Path, script_path: Path) -> None:
    import sqlite3

    sql = script_path.read_text(encoding="utf-8")
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(sql)
        conn.commit()
    finally:
        conn.close()


def _sqlite_columns(conn: object, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row[1]) for row in rows}


def _apply_sqlite_migrations(db_path: Path) -> None:
    """Keep existing development SQLite databases compatible with current models.

    schema.sql uses CREATE TABLE IF NOT EXISTS, so it cannot add columns to an
    already-created table. These targeted ALTERs prevent 500s after model fields
    are added while keeping the database contents intact.
    """
    import sqlite3

    conn = sqlite3.connect(db_path)
    try:
        tables = {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "appUser" in tables:
            cols = _sqlite_columns(conn, "appUser")
            if "language" not in cols:
                conn.execute("ALTER TABLE appUser ADD COLUMN language VARCHAR(10) NOT NULL DEFAULT 'zh'")
            if "avatarUrl" not in cols:
                conn.execute("ALTER TABLE appUser ADD COLUMN avatarUrl VARCHAR(500)")
            if "updatedAt" not in cols:
                conn.execute("ALTER TABLE appUser ADD COLUMN updatedAt VARCHAR(64)")
                conn.execute("UPDATE appUser SET updatedAt = COALESCE(createdAt, strftime('%Y-%m-%dT%H:%M:%f+08:00', 'now')) WHERE updatedAt IS NULL")
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    from app.new_core import models  # noqa: F401

    settings = get_settings()
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    if settings.database_url.startswith("sqlite"):
        _execute_sqlite_script(settings.database_path, schemaSqlPath())
        _apply_sqlite_migrations(settings.database_path)
        return

    engine, _ = _ensure_engine()
    Base.metadata.create_all(bind=engine)
