from pathlib import Path

_SQL_DIR = Path(__file__).resolve().parent / "sql"


def schemaSqlPath() -> Path:
    return _SQL_DIR / "schema.sql"


def devicePhotoSqlPath() -> Path:
    return _SQL_DIR / "device_photo_request.sql"


def dropSqlPath() -> Path:
    return _SQL_DIR / "drop.sql"
