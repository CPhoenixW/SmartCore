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


def _sqlite_table_info(conn: object, table: str) -> list[tuple]:
    return list(conn.execute(f"PRAGMA table_info({table})").fetchall())


def _sqlite_table_sql(conn: object, table: str) -> str:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return str(row[0] or "") if row else ""


def _add_sqlite_column(conn: object, table: str, column: str, ddl: str) -> None:
    if column not in _sqlite_columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def _rebuild_table_if_incompatible(conn: object, table: str, required_columns: set[str], create_sql: str) -> None:
    cols = _sqlite_columns(conn, table)
    if not required_columns.issubset(cols):
        conn.execute(f"DROP TABLE IF EXISTS {table}")
        conn.execute(create_sql)


def _evt_base_supports_reminders(conn: object) -> bool:
    return "'remind'" in _sqlite_table_sql(conn, "evtBase")


def _rebuild_evt_base_for_reminders(conn: object) -> None:
    if not _sqlite_columns(conn, "evtBase") or _evt_base_supports_reminders(conn):
        return
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


def _rebuild_remind_evt_for_standalone(conn: object) -> None:
    if not _sqlite_columns(conn, "remindEvt"):
        return
    info = {str(row[1]): row for row in _sqlite_table_info(conn, "remindEvt")}
    sql = _sqlite_table_sql(conn, "remindEvt")
    plan_not_null = bool(info.get("planEvtId") and int(info["planEvtId"][3]) == 1)
    constrained_kinds = "remindKind IN" in sql
    has_ddl_link = "ddlEvtId" in _sqlite_columns(conn, "remindEvt")
    exclusive_owner = "planEvtId IS NULL OR ddlEvtId IS NULL" in sql
    if not plan_not_null and not constrained_kinds and has_ddl_link and exclusive_owner:
        return

    conn.execute("DROP TABLE IF EXISTS remindEvt_new")
    conn.execute(
        """
        CREATE TABLE remindEvt_new (
            evtId VARCHAR(32) PRIMARY KEY,
            planEvtId VARCHAR(32),
            ddlEvtId VARCHAR(32),
            remindKind VARCHAR(30) NOT NULL,
            triggerTime VARCHAR(64) NOT NULL,
            offsetMin INTEGER NOT NULL DEFAULT 0,
            firedAt VARCHAR(64),
            FOREIGN KEY (evtId) REFERENCES evtBase(evtId) ON DELETE CASCADE,
            FOREIGN KEY (planEvtId) REFERENCES planEvt(evtId) ON DELETE CASCADE,
            FOREIGN KEY (ddlEvtId) REFERENCES ddlEvt(evtId) ON DELETE CASCADE,
            UNIQUE (planEvtId, remindKind),
            CHECK (offsetMin >= 0),
            CHECK (planEvtId IS NULL OR ddlEvtId IS NULL)
        )
        """
    )
    conn.execute(
        """
        INSERT INTO remindEvt_new (
            evtId, planEvtId, ddlEvtId, remindKind, triggerTime, offsetMin, firedAt
        )
        SELECT
            evtId, planEvtId, NULL, remindKind, triggerTime, COALESCE(offsetMin, 0), firedAt
        FROM remindEvt
        """
    )
    conn.execute("DROP TABLE remindEvt")
    conn.execute("ALTER TABLE remindEvt_new RENAME TO remindEvt")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_remindEvt_trigger ON remindEvt(triggerTime)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_remindEvt_plan ON remindEvt(planEvtId)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_remindEvt_ddl_trigger ON remindEvt(ddlEvtId, triggerTime)")


def _rebuild_act_log_for_user_targets(conn: object) -> None:
    sql = _sqlite_table_sql(conn, "actLog")
    if not _sqlite_columns(conn, "actLog") or "CHECK (targetKind IN ('user'," in sql:
        return
    conn.execute("DROP TABLE IF EXISTS actLog_new")
    conn.execute(
        """
        CREATE TABLE actLog_new (
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
            createdAt VARCHAR(64) NOT NULL,
            CHECK (actorKind IN ('user', 'system', 'device', 'llm')),
            CHECK (action IN ('create', 'update', 'delete', 'complete', 'cancel', 'auto_create', 'link', 'notify')),
            CHECK (targetKind IN ('user', 'evt', 'planEvt', 'ddlEvt', 'courseEvt', 'remindEvt', 'coursePlan', 'idea', 'device')),
            CHECK (result IN ('ok', 'failed'))
        )
        """
    )
    conn.execute("INSERT INTO actLog_new SELECT * FROM actLog")
    conn.execute("DROP TABLE actLog")
    conn.execute("ALTER TABLE actLog_new RENAME TO actLog")


def _repair_duplicate_login_names(conn: object) -> None:
    """Retire generated passwordless shadows before enforcing unique login names."""
    if not _sqlite_columns(conn, "appUser"):
        return
    duplicates = conn.execute(
        "SELECT loginName FROM appUser WHERE loginName IS NOT NULL "
        "GROUP BY loginName HAVING COUNT(*) > 1"
    ).fetchall()
    for (login_name,) in duplicates:
        rows = conn.execute(
            "SELECT userId, passwd, displayName FROM appUser WHERE loginName = ? ORDER BY createdAt",
            (login_name,),
        ).fetchall()
        keeper = next((row for row in rows if row[1]), rows[0])
        for user_id, password, display_name in rows:
            if user_id == keeper[0] or password or display_name != "默认用户":
                continue
            conn.execute(
                "UPDATE appUser SET loginName = NULL, stat = 'disabled' WHERE userId = ?",
                (user_id,),
            )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_appUser_loginName ON appUser(loginName) "
        "WHERE loginName IS NOT NULL"
    )


def _rebuild_ddl_plan_for_multiple_links(conn: object) -> None:
    if not _sqlite_columns(conn, "ddlPlan"):
        return
    sql = _sqlite_table_sql(conn, "ddlPlan")
    if "UNIQUE (ddlEvtId, planRole)" not in sql and "UNIQUE(ddlEvtId, planRole)" not in sql:
        return

    conn.execute("DROP TRIGGER IF EXISTS trg_cancel_ddl_linked_plans")
    conn.execute("DROP TABLE IF EXISTS ddlPlan_new")
    conn.execute(
        """
        CREATE TABLE ddlPlan_new (
            ddlEvtId VARCHAR(32) NOT NULL,
            planEvtId VARCHAR(32) NOT NULL,
            planRole VARCHAR(30) NOT NULL,
            sortOrder INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (ddlEvtId, planEvtId),
            FOREIGN KEY (ddlEvtId) REFERENCES ddlEvt(evtId) ON DELETE CASCADE,
            FOREIGN KEY (planEvtId) REFERENCES planEvt(evtId) ON DELETE CASCADE,
            UNIQUE (planEvtId),
            CHECK (planRole IN ('one_day_before', 'one_hour_before', 'manual'))
        )
        """
    )
    conn.execute(
        """
        INSERT INTO ddlPlan_new (ddlEvtId, planEvtId, planRole, sortOrder)
        SELECT ddlEvtId, planEvtId, planRole, COALESCE(sortOrder, 0)
        FROM ddlPlan
        """
    )
    conn.execute("DROP TABLE ddlPlan")
    conn.execute("ALTER TABLE ddlPlan_new RENAME TO ddlPlan")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ddlPlan_ddl_order ON ddlPlan(ddlEvtId, sortOrder)")


def _apply_sqlite_migrations(db_path: Path) -> None:
    """Keep existing development SQLite databases compatible with current models."""
    import sqlite3

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        tables = {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "appUser" in tables:
            _add_sqlite_column(conn, "appUser", "loginName", "loginName VARCHAR(100)")
            _add_sqlite_column(conn, "appUser", "role", "role VARCHAR(20) NOT NULL DEFAULT 'user'")
            _add_sqlite_column(conn, "appUser", "stat", "stat VARCHAR(20) NOT NULL DEFAULT 'active'")
            _add_sqlite_column(conn, "appUser", "sessionVersion", "sessionVersion INTEGER NOT NULL DEFAULT 1")
            _add_sqlite_column(conn, "appUser", "lastLoginAt", "lastLoginAt VARCHAR(64)")
            _add_sqlite_column(conn, "appUser", "language", "language VARCHAR(10) NOT NULL DEFAULT 'zh'")
            _add_sqlite_column(conn, "appUser", "avatarUrl", "avatarUrl VARCHAR(500)")
            _add_sqlite_column(conn, "appUser", "updatedAt", "updatedAt VARCHAR(64)")
            conn.execute("UPDATE appUser SET role = CASE WHEN userId = 'default' THEN 'admin' ELSE COALESCE(role, 'user') END")
            conn.execute("UPDATE appUser SET language = COALESCE(language, 'zh')")
            conn.execute("UPDATE appUser SET updatedAt = COALESCE(updatedAt, createdAt, strftime('%Y-%m-%dT%H:%M:%f+08:00', 'now')) WHERE updatedAt IS NULL")
            _repair_duplicate_login_names(conn)
        if "evtBase" in tables:
            _add_sqlite_column(conn, "evtBase", "userId", "userId VARCHAR(32) NOT NULL DEFAULT 'default'")
            conn.execute("UPDATE evtBase SET userId = COALESCE(userId, 'default')")
            _rebuild_evt_base_for_reminders(conn)
        if "remindEvt" in tables:
            _rebuild_remind_evt_for_standalone(conn)
        if "ddlPlan" in tables:
            _rebuild_ddl_plan_for_multiple_links(conn)
        if "idea" in tables:
            _add_sqlite_column(conn, "idea", "userId", "userId VARCHAR(32) NOT NULL DEFAULT 'default'")
            conn.execute("UPDATE idea SET userId = COALESCE(userId, 'default')")
        if "actLog" in tables:
            _rebuild_act_log_for_user_targets(conn)
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
        if "devicePair" in tables:
            _add_sqlite_column(conn, "devicePair", "botId", "botId VARCHAR(32)")
        conn.commit()
        conn.execute("PRAGMA foreign_keys = ON")
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
        from app.feishu.bot_service import seedLegacyBot

        db = SessionLocal()
        try:
            seedLegacyBot(db, settings)
        finally:
            db.close()
        return

    engine, _ = _ensure_engine()
    Base.metadata.create_all(bind=engine)
    from app.feishu.bot_service import seedLegacyBot

    db = SessionLocal()
    try:
        seedLegacyBot(db, settings)
    finally:
        db.close()
