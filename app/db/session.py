from collections.abc import Callable, Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings
from app.db.schema_paths import devicePhotoSqlPath, schemaSqlPath


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


def _add_sqlite_column(conn: object, table: str, column: str, ddl: str) -> None:
    if column not in _sqlite_columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def _rebuild_table_if_incompatible(conn: object, table: str, required_columns: set[str], create_sql: str) -> None:
    cols = _sqlite_columns(conn, table)
    if not required_columns.issubset(cols):
        conn.execute(f"DROP TABLE IF EXISTS {table}")
        conn.execute(create_sql)


def _evt_base_supports_reminders(conn: object) -> bool:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='evtBase'"
    ).fetchone()
    return bool(row and row[0] and "'remind'" in str(row[0]))


def _rebuild_evt_base_for_reminders(conn: object) -> None:
    if not _sqlite_columns(conn, "evtBase") or _evt_base_supports_reminders(conn):
        return
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("DROP TABLE IF EXISTS evtBase_new")
    conn.execute(
        """
        CREATE TABLE evtBase_new (
            evtId VARCHAR(32) PRIMARY KEY,
            userId VARCHAR(32) NOT NULL,
            title VARCHAR(300) NOT NULL,
            desc TEXT,
            evtType VARCHAR(20) NOT NULL,
            prio VARCHAR(10) NOT NULL DEFAULT 'mid',
            stat VARCHAR(20) NOT NULL DEFAULT 'todo',
            createdAt VARCHAR(64) NOT NULL,
            updatedAt VARCHAR(64) NOT NULL,
            FOREIGN KEY (userId) REFERENCES appUser(userId) ON DELETE CASCADE,
            CHECK (evtType IN ('plan', 'ddl', 'course', 'remind')),
            CHECK (prio IN ('low', 'mid', 'high')),
            CHECK (stat IN ('todo', 'done', 'cancelled'))
        )
        """
    )
    columns = _sqlite_columns(conn, "evtBase")
    user_expr = "COALESCE(userId, 'default')" if "userId" in columns else "'default'"
    updated_expr = "COALESCE(updatedAt, createdAt)" if "updatedAt" in columns else "createdAt"
    conn.execute(
        f"""
        INSERT INTO evtBase_new (
            evtId, userId, title, desc, evtType, prio, stat, createdAt, updatedAt
        )
        SELECT
            evtId, {user_expr}, title, desc, evtType,
            COALESCE(prio, 'mid'), COALESCE(stat, 'todo'), createdAt, {updated_expr}
        FROM evtBase
        """
    )
    conn.execute("DROP TABLE evtBase")
    conn.execute("ALTER TABLE evtBase_new RENAME TO evtBase")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_evtBase_user_stat_time ON evtBase(userId, stat, updatedAt)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_evtBase_user_type ON evtBase(userId, evtType)")
    conn.execute("PRAGMA foreign_keys = ON")


def _apply_sqlite_migrations(db_path: Path) -> None:
    """Keep existing development SQLite databases compatible with current models."""
    import sqlite3

    conn = sqlite3.connect(db_path)
    try:
        tables = {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "appUser" in tables:
            _add_sqlite_column(conn, "appUser", "language", "language VARCHAR(10) NOT NULL DEFAULT 'zh'")
            _add_sqlite_column(conn, "appUser", "avatarUrl", "avatarUrl VARCHAR(500)")
            _add_sqlite_column(conn, "appUser", "updatedAt", "updatedAt VARCHAR(64)")
            conn.execute("UPDATE appUser SET language = COALESCE(language, 'zh')")
            conn.execute("UPDATE appUser SET updatedAt = COALESCE(updatedAt, createdAt, strftime('%Y-%m-%dT%H:%M:%f+08:00', 'now')) WHERE updatedAt IS NULL")
        if "evtBase" in tables:
            _add_sqlite_column(conn, "evtBase", "userId", "userId VARCHAR(32) NOT NULL DEFAULT 'default'")
            conn.execute("UPDATE evtBase SET userId = COALESCE(userId, 'default')")
            _rebuild_evt_base_for_reminders(conn)
        if "idea" in tables:
            _add_sqlite_column(conn, "idea", "userId", "userId VARCHAR(32) NOT NULL DEFAULT 'default'")
            conn.execute("UPDATE idea SET userId = COALESCE(userId, 'default')")
        if "actLog" in tables:
            _rebuild_table_if_incompatible(
                conn,
                "actLog",
                {"actId", "userId", "actorKind", "actorId", "action", "targetKind", "targetId", "sourceDeviceId", "result", "errorMessage", "createdAt"},
                """
                CREATE TABLE actLog (
                    actId VARCHAR(32) PRIMARY KEY,
                    userId VARCHAR(32) NOT NULL,
                    actorKind VARCHAR(20) NOT NULL,
                    actorId VARCHAR(100),
                    action VARCHAR(30) NOT NULL,
                    targetKind VARCHAR(30) NOT NULL,
                    targetId VARCHAR(32) NOT NULL,
                    sourceDeviceId VARCHAR(50),
                    result VARCHAR(20) NOT NULL DEFAULT 'ok',
                    errorMessage TEXT,
                    createdAt VARCHAR(64) NOT NULL
                )
                """,
            )
        if "notifyLog" in tables:
            _rebuild_table_if_incompatible(
                conn,
                "notifyLog",
                {"notifyId", "userId", "evtId", "channel", "receiver", "sourceDeviceId", "routeReason", "title", "content", "scheduledAt", "sentAt", "stat", "failReason", "dedupKey"},
                """
                CREATE TABLE notifyLog (
                    notifyId VARCHAR(32) PRIMARY KEY,
                    userId VARCHAR(32) NOT NULL,
                    evtId VARCHAR(32),
                    channel VARCHAR(20) NOT NULL,
                    receiver VARCHAR(100),
                    sourceDeviceId VARCHAR(50),
                    routeReason VARCHAR(50),
                    title VARCHAR(300) NOT NULL,
                    content TEXT NOT NULL,
                    scheduledAt VARCHAR(64) NOT NULL,
                    sentAt VARCHAR(64),
                    stat VARCHAR(20) NOT NULL,
                    failReason TEXT,
                    dedupKey VARCHAR(200) UNIQUE
                )
                """,
            )
        if "msgLog" in tables:
            _rebuild_table_if_incompatible(
                conn,
                "msgLog",
                {"msgId", "userId", "channel", "direction", "externalId", "sourceDeviceId", "rawText", "intent", "stat", "createdAt"},
                """
                CREATE TABLE msgLog (
                    msgId VARCHAR(32) PRIMARY KEY,
                    userId VARCHAR(32) NOT NULL,
                    channel VARCHAR(30) NOT NULL,
                    direction VARCHAR(10) NOT NULL,
                    externalId VARCHAR(200),
                    sourceDeviceId VARCHAR(50),
                    rawText TEXT,
                    intent VARCHAR(100),
                    stat VARCHAR(50),
                    createdAt VARCHAR(64) NOT NULL
                )
                """,
            )
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    from app.new_core import models  # noqa: F401

    settings = get_settings()
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    if settings.database_url.startswith("sqlite"):
        if settings.database_path.exists():
            _apply_sqlite_migrations(settings.database_path)
        _execute_sqlite_script(settings.database_path, schemaSqlPath())
        _execute_sqlite_script(settings.database_path, devicePhotoSqlPath())
        _apply_sqlite_migrations(settings.database_path)
        engine, _ = _ensure_engine()
        Base.metadata.create_all(bind=engine)
        return

    engine, _ = _ensure_engine()
    Base.metadata.create_all(bind=engine)
