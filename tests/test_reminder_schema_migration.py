from __future__ import annotations

import sqlite3

from app.db.session import _apply_sqlite_migrations


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
