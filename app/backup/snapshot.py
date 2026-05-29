"""SQLite consistent snapshots and local retention."""

from __future__ import annotations

import gzip
import re
import shutil
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.config import Settings, get_settings

SNAPSHOT_NAME_PATTERN = re.compile(r"^smartcore-(\d{4}-\d{2}-\d{2}-\d{6})\.sqlite\.gz$")
SNAPSHOT_TIMESTAMP_FORMAT = "%Y-%m-%d-%H%M%S"


def snapshot_filename(when: datetime | None = None) -> str:
    moment = when or datetime.now(UTC)
    return f"smartcore-{moment.strftime(SNAPSHOT_TIMESTAMP_FORMAT)}.sqlite.gz"


def parse_snapshot_timestamp(filename: str) -> datetime | None:
    match = SNAPSHOT_NAME_PATTERN.match(Path(filename).name)
    if match is None:
        return None
    try:
        return datetime.strptime(match.group(1), SNAPSHOT_TIMESTAMP_FORMAT).replace(tzinfo=UTC)
    except ValueError:
        return None


def create_snapshot(
    source_db: Path,
    backup_dir: Path,
    when: datetime | None = None,
) -> Path:
    """Create a gzip-compressed SQLite backup using the online backup API."""
    if not source_db.exists():
        raise FileNotFoundError(f"Database not found: {source_db}")

    backup_dir.mkdir(parents=True, exist_ok=True)
    archive_path = backup_dir / snapshot_filename(when)
    temp_sqlite = backup_dir / f".tmp-{archive_path.stem}"

    try:
        with sqlite3.connect(source_db) as source_conn, sqlite3.connect(temp_sqlite) as dest_conn:
            source_conn.backup(dest_conn)

        with temp_sqlite.open("rb") as plain, gzip.open(archive_path, "wb") as compressed:
            shutil.copyfileobj(plain, compressed)
    finally:
        temp_sqlite.unlink(missing_ok=True)

    return archive_path


def cleanup_local_backups(
    backup_dir: Path,
    retention_days: int = 30,
    when: datetime | None = None,
) -> list[Path]:
    """Delete local snapshots older than the retention window."""
    if not backup_dir.exists():
        return []

    cutoff = (when or datetime.now(UTC)) - timedelta(days=retention_days)
    removed: list[Path] = []

    for path in sorted(backup_dir.glob("smartcore-*.sqlite.gz")):
        snapshot_time = parse_snapshot_timestamp(path.name)
        if snapshot_time is None or snapshot_time >= cutoff:
            continue
        path.unlink()
        removed.append(path)

    return removed


def restore_snapshot(
    backup_file: Path,
    target_db: Path,
    *,
    save_current: bool = True,
) -> Path | None:
    """Restore a gzip snapshot to the live database path."""
    if not backup_file.is_file():
        raise FileNotFoundError(f"Backup file not found: {backup_file}")

    saved_current: Path | None = None
    if save_current and target_db.exists():
        saved_current = target_db.with_name(f"{target_db.name}.before-restore")
        shutil.copy2(target_db, saved_current)

    target_db.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(backup_file, "rb") as compressed, target_db.open("wb") as restored:
        shutil.copyfileobj(compressed, restored)

    return saved_current


def run_local_backup(settings: Settings | None = None) -> Path:
    """Create a snapshot and prune expired local backups."""
    cfg = settings or get_settings()
    archive = create_snapshot(cfg.database_path, cfg.backup_path)
    cleanup_local_backups(cfg.backup_path, cfg.local_backup_retention_days)
    return archive
