import re
import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.backup.snapshot import (
    cleanup_local_backups,
    create_snapshot,
    parse_snapshot_timestamp,
    restore_snapshot,
    run_local_backup,
    snapshot_filename,
)
from app.backup.sync_to_pi import build_remote_cleanup_command, build_rsync_command, sync_to_pi
from app.config import get_settings


@pytest.fixture
def backup_settings(tmp_path, monkeypatch):
    db_path = tmp_path / "data" / "smartcore.sqlite"
    backup_dir = tmp_path / "backups"
    db_path.parent.mkdir(parents=True)
    backup_dir.mkdir()

    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO sample (value) VALUES ('phase7')")
        conn.commit()

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("BACKUP_DIR", str(backup_dir))
    get_settings.cache_clear()
    settings = get_settings()
    yield settings
    get_settings.cache_clear()


def test_snapshot_filename_format():
    moment = datetime(2026, 5, 29, 3, 0, 0, tzinfo=UTC)
    assert snapshot_filename(moment) == "smartcore-2026-05-29-030000.sqlite.gz"
    assert re.fullmatch(r"smartcore-\d{4}-\d{2}-\d{2}-\d{6}\.sqlite\.gz", snapshot_filename(moment))


def test_create_snapshot_uses_sqlite_backup(backup_settings):
    archive = create_snapshot(
        backup_settings.database_path,
        backup_settings.backup_path,
        when=datetime(2026, 5, 29, 3, 0, 0, tzinfo=UTC),
    )

    assert archive.name == "smartcore-2026-05-29-030000.sqlite.gz"
    assert archive.exists()

    restored_db = backup_settings.database_path.parent / "restored.sqlite"
    restore_snapshot(archive, restored_db, save_current=False)

    with sqlite3.connect(restored_db) as conn:
        row = conn.execute("SELECT value FROM sample").fetchone()
    assert row == ("phase7",)


def test_cleanup_local_backups_removes_expired(backup_settings):
    backup_dir = backup_settings.backup_path
    old_name = snapshot_filename(datetime(2026, 3, 1, 3, 0, 0, tzinfo=UTC))
    recent_name = snapshot_filename(datetime(2026, 5, 20, 3, 0, 0, tzinfo=UTC))
    (backup_dir / old_name).write_bytes(b"old")
    (backup_dir / recent_name).write_bytes(b"recent")

    removed = cleanup_local_backups(
        backup_dir,
        retention_days=30,
        when=datetime(2026, 5, 29, 3, 0, 0, tzinfo=UTC),
    )

    assert removed == [backup_dir / old_name]
    assert not (backup_dir / old_name).exists()
    assert (backup_dir / recent_name).exists()


def test_run_local_backup_creates_and_prunes(backup_settings, monkeypatch):
    backup_dir = backup_settings.backup_path
    expired = snapshot_filename(datetime(2026, 3, 1, 3, 0, 0, tzinfo=UTC))
    (backup_dir / expired).write_bytes(b"expired")

    fixed_now = datetime(2026, 5, 29, 3, 0, 0, tzinfo=UTC)
    monkeypatch.setattr("app.backup.snapshot.datetime", type("FixedDateTime", (), {
        "now": staticmethod(lambda tz=None: fixed_now),
        "strptime": datetime.strptime,
    }))

    archive = run_local_backup(backup_settings)
    assert archive.name == snapshot_filename(fixed_now)
    assert archive.exists()
    assert not (backup_dir / expired).exists()


def test_build_rsync_command_supports_dry_run(backup_settings):
    backup_settings.pi_user = "pi"
    backup_settings.pi_host = "raspberrypi"
    backup_settings.pi_backup_dir = "/home/pi/smartcore-backups"

    command = build_rsync_command(backup_settings.backup_path, backup_settings, dry_run=True)
    assert command[:3] == ["rsync", "--dry-run", "-av"]
    assert command[-1] == "pi@raspberrypi:/home/pi/smartcore-backups/"


def test_sync_to_pi_dry_run_uses_mock_runner(backup_settings):
    backup_settings.pi_user = "pi"
    backup_settings.pi_host = "raspberrypi"
    backup_settings.pi_backup_dir = "/home/pi/smartcore-backups"

    captured: dict[str, list[str]] = {}

    def mock_runner(command):
        captured["command"] = list(command)

        class Result:
            returncode = 0
            stdout = "dry run"
            stderr = ""

        return Result()

    result = sync_to_pi(settings=backup_settings, dry_run=True, runner=mock_runner)

    assert captured["command"][1] == "--dry-run"
    assert result.stdout == "dry run"


def test_remote_cleanup_command_uses_retention_days(backup_settings):
    backup_settings.pi_user = "pi"
    backup_settings.pi_host = "raspberrypi"
    backup_settings.pi_backup_dir = "/home/pi/smartcore-backups"
    backup_settings.pi_backup_retention_days = 90

    command = build_remote_cleanup_command(backup_settings)
    assert command[0] == "ssh"
    assert command[1] == "pi@raspberrypi"
    assert "-mtime +90" in command[2]


def test_parse_snapshot_timestamp():
    parsed = parse_snapshot_timestamp("smartcore-2026-05-29-030000.sqlite.gz")
    assert parsed == datetime(2026, 5, 29, 3, 0, 0, tzinfo=UTC)
    assert parse_snapshot_timestamp("invalid-name.gz") is None


def test_restore_script_requires_backup_file():
    script = Path(__file__).resolve().parents[1] / "scripts" / "restore_backup.sh"
    result = subprocess.run(
        [str(script)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "must be explicitly specified" in result.stderr
