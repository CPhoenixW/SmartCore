import re

from sqlalchemy import inspect

from app.db.schema_paths import dropSqlPath, schemaSqlPath
from app.db.session import SessionLocal, init_db
from app.new_core.reset_db import resetDatabase, resetDatabaseScriptPaths

EXPECTED_TABLES = frozenset(
    {
        "evtBase",
        "lifeEvt",
        "ddlEvt",
        "courseTpl",
        "courseInst",
        "idea",
        "ideaToEvt",
        "devState",
        "notifyLog",
        "msgLog",
        "actLog",
    }
)


def test_schema_sql_exists_and_uses_lower_camel_table_names() -> None:
    schema_path = schemaSqlPath()
    assert schema_path.is_file()

    sql = schema_path.read_text(encoding="utf-8")
    for table in EXPECTED_TABLES:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql

    snake_tables = re.findall(r"CREATE TABLE IF NOT EXISTS ([a-z]+_[a-z0-9_]+)", sql)
    assert snake_tables == []


def test_drop_sql_exists_and_drops_new_arch_tables() -> None:
    drop_path = dropSqlPath()
    assert drop_path.is_file()

    sql = drop_path.read_text(encoding="utf-8")
    for table in EXPECTED_TABLES:
        assert f"DROP TABLE IF EXISTS {table}" in sql


def test_init_db_creates_exactly_expected_new_tables(app_env) -> None:
    init_db()
    db = SessionLocal()
    try:
        tables = set(inspect(db.get_bind()).get_table_names())
    finally:
        db.close()

    assert tables == set(EXPECTED_TABLES)


def test_reset_database_script_paths_point_at_sql_files() -> None:
    drop_path, schema_path = resetDatabaseScriptPaths()
    assert drop_path == dropSqlPath()
    assert schema_path == schemaSqlPath()


def test_reset_database_removes_unknown_legacy_tables(app_env) -> None:
    from sqlalchemy import text

    init_db()
    db = SessionLocal()
    try:
        db.execute(text("CREATE TABLE oldTable (id INTEGER PRIMARY KEY)"))
        db.commit()
    finally:
        db.close()

    resetDatabase()

    db = SessionLocal()
    try:
        tables = set(inspect(db.get_bind()).get_table_names())
    finally:
        db.close()

    assert tables == set(EXPECTED_TABLES)
