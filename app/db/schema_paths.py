from pathlib import Path

_SQL_DIR = Path(__file__).resolve().parent / "sql"


def schemaSqlPath() -> Path:
    return _SQL_DIR / "schema.sql"


def dropSqlPath() -> Path:
    return _SQL_DIR / "drop.sql"
