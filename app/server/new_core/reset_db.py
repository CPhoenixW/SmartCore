from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.server.config import get_settings
from app.server.db.schema_paths import dropSqlPath, schemaSqlPath
from app.server.db.session import SessionLocal, dispose_engine, init_db

_DEFAULT_TZ = ZoneInfo("Asia/Shanghai")


def _remove_sqlite_files(db_path: Path) -> None:
    for path in (db_path, Path(f"{db_path}-wal"), Path(f"{db_path}-shm")):
        if path.exists():
            path.unlink()


def resetDatabaseScriptPaths() -> tuple[Path, Path]:
    return dropSqlPath(), schemaSqlPath()


def resetDatabase() -> Path | None:
    settings = get_settings()
    db_path = settings.database_path
    if not db_path.exists():
        init_db()
        return None

    backup_dir = settings.backup_path
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(_DEFAULT_TZ).strftime("%Y%m%d-%H%M%S")
    backup_path = backup_dir / f"smartcore-{stamp}.sqlite"
    shutil.copy2(db_path, backup_path)

    dispose_engine()
    _remove_sqlite_files(db_path)
    init_db()
    return backup_path


def resetDatabaseFromCli() -> int:
    backup = resetDatabase()
    db = SessionLocal()
    try:
        from app.server.new_core import crud

        assert crud.listEvt(db) == []
    finally:
        db.close()
    if backup is None:
        print("Database initialized.")
    else:
        print(f"Database reset. Backup: {backup}")
    return 0
