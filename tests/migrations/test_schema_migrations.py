from __future__ import annotations

import sqlite3

import pytest

from app.server.db.session import _apply_sqlite_migrations, init_db

pytestmark = pytest.mark.migration


def test_existing_evt_base_is_rebuilt_for_reminder_type(tmp_path) -> None:
    database = tmp_path / "legacy.sqlite"
    conn = sqlite3.connect(database)
    try:
        conn.executescript(
            """
            CREATE TABLE appUser (
                userId VARCHAR(32) PRIMARY KEY,
                displayName VARCHAR(100) NOT NULL,
                createdAt VARCHAR(64) NOT NULL
            );
            INSERT INTO appUser(userId, displayName, createdAt)
            VALUES ('default', 'Default', '2026-07-09T00:00:00+08:00');

            CREATE TABLE evtBase (
                evtId VARCHAR(32) PRIMARY KEY,
                userId VARCHAR(32) NOT NULL,
                title VARCHAR(300) NOT NULL,
                desc TEXT,
                evtType VARCHAR(20) NOT NULL,
                prio VARCHAR(10) NOT NULL DEFAULT 'mid',
                stat VARCHAR(20) NOT NULL DEFAULT 'todo',
                createdAt VARCHAR(64) NOT NULL,
                updatedAt VARCHAR(64) NOT NULL,
                CHECK (evtType IN ('plan', 'ddl', 'course'))
            );
            INSERT INTO evtBase(
                evtId, userId, title, evtType, prio, stat, createdAt, updatedAt
            ) VALUES (
                'plan-1', 'default', 'Plan', 'plan', 'mid', 'todo',
                '2026-07-09T00:00:00+08:00', '2026-07-09T00:00:00+08:00'
            );
            """
        )
        conn.commit()
    finally:
        conn.close()

    _apply_sqlite_migrations(database)

    conn = sqlite3.connect(database)
    try:
        conn.execute(
            """
            INSERT INTO evtBase(
                evtId, userId, title, evtType, prio, stat, createdAt, updatedAt
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "remind-1",
                "default",
                "Reminder",
                "remind",
                "mid",
                "todo",
                "2026-07-09T00:00:00+08:00",
                "2026-07-09T00:00:00+08:00",
            ),
        )
        conn.commit()
        rows = conn.execute("SELECT evtType FROM evtBase ORDER BY evtId").fetchall()
        assert rows == [("plan",), ("remind",)]
    finally:
        conn.close()


def test_sqlite_revision_migration_preserves_idea_and_attachment(app_env, tmp_path) -> None:
    init_db()
    attachment_path = tmp_path / "kept.txt"
    attachment_path.write_text("keep me", encoding="utf-8")
    with sqlite3.connect(app_env) as conn:
        conn.execute("ALTER TABLE idea DROP COLUMN revision")
        conn.execute(
            """
            INSERT INTO idea (ideaId, userId, title, description, srcType, handled, createdAt)
            VALUES ('idea-kept', 'default', 'Keep', 'Existing description', 'text', 0, 'now')
            """
        )
        conn.execute(
            """
            INSERT INTO ideaAttachment
                (attachmentId, ideaId, fileName, mimeType, storagePath, sizeBytes, createdAt)
            VALUES (?, 'idea-kept', 'kept.txt', 'text/plain', ?, 7, 'now')
            """,
            ("attachment-kept", str(attachment_path)),
        )
        conn.commit()

    init_db()

    with sqlite3.connect(app_env) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(idea)")}
        idea_row = conn.execute(
            "SELECT title, description, revision FROM idea WHERE ideaId = 'idea-kept'"
        ).fetchone()
        attachment_row = conn.execute(
            "SELECT fileName, storagePath FROM ideaAttachment WHERE attachmentId = 'attachment-kept'"
        ).fetchone()
        media_job_table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'ideaMediaJob'"
        ).fetchone()

    assert "revision" in columns
    assert idea_row == ("Keep", "Existing description", 1)
    assert attachment_row == ("kept.txt", str(attachment_path))
    assert media_job_table == ("ideaMediaJob",)


def test_computer_activity_schema_is_additive_and_idempotent(app_env) -> None:
    init_db()
    init_db()
    expected_tables = {
        "computerActivityContext",
        "computerActivityBucket",
        "computerActivitySlice",
        "computerMonitorStatus",
        "computerDailyUsage",
        "computerDailyAppUsage",
        "computerHourlyAnalysis",
        "computerDailyWorkLog",
        "computerWorkBlock",
        "computerWorkBlockAnalysisRun",
    }
    with sqlite3.connect(app_env) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        indexes = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        context_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(computerActivityContext)")
        }
        daily_log_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(computerDailyWorkLog)")
        }
        quick_check = conn.execute("PRAGMA quick_check").fetchone()
        foreign_keys = conn.execute("PRAGMA foreign_key_check").fetchall()

    assert expected_tables <= tables
    assert "idx_computer_bucket_device_start" in indexes
    assert "idx_computer_hourly_user_date" in indexes
    assert "idx_computer_daily_log_user_date" in indexes
    assert "idx_computer_work_block_user_date" in indexes
    assert {"contextKind", "domain", "workspace", "documentName"} <= context_columns
    assert {"attemptCount", "lastAttemptAt", "leaseExpiresAt", "nextRetryAt"} <= daily_log_columns
    assert quick_check == ("ok",)
    assert [row for row in foreign_keys if str(row[0]).startswith("computer")] == []


def test_existing_computer_context_table_gets_optional_structured_columns(tmp_path) -> None:
    database = tmp_path / "legacy-computer.sqlite"
    with sqlite3.connect(database) as conn:
        conn.execute(
            """
            CREATE TABLE computerActivityContext (
                contextId VARCHAR(32) PRIMARY KEY,
                userId VARCHAR(32) NOT NULL,
                fingerprint VARCHAR(64) NOT NULL,
                bundleId VARCHAR(300) NOT NULL,
                appName VARCHAR(200) NOT NULL,
                windowTitle VARCHAR(300),
                titleRedacted BOOLEAN NOT NULL DEFAULT 0,
                firstSeenAt VARCHAR(64) NOT NULL,
                lastSeenAt VARCHAR(64) NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO computerActivityContext VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("context-1", "user-1", "hash", "com.example.Editor", "Editor", "notes.txt", 0, "now", "now"),
        )

    _apply_sqlite_migrations(database)
    _apply_sqlite_migrations(database)

    with sqlite3.connect(database) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(computerActivityContext)")}
        row = conn.execute(
            "SELECT bundleId, windowTitle, contextKind, domain, workspace, documentName "
            "FROM computerActivityContext WHERE contextId = 'context-1'"
        ).fetchone()
    assert {"contextKind", "domain", "workspace", "documentName"} <= columns
    assert row == ("com.example.Editor", "notes.txt", None, None, None, None)
