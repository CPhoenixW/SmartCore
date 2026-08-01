from __future__ import annotations

import hashlib

from sqlalchemy import inspect, text

from app.server.db.session import SessionLocal


def ensure_auth_schema() -> None:
    """Add authentication columns to existing databases without dropping user data."""
    db = SessionLocal()
    try:
        bind = db.get_bind()
        columns = {str(column["name"]) for column in inspect(bind).get_columns("appUser")}
        if "passwd" not in columns:
            db.execute(text("ALTER TABLE appUser ADD COLUMN passwd VARCHAR(255)"))
        session_columns = {
            str(column["name"]) for column in inspect(bind).get_columns("userSession")
        }
        if "tokenHash" not in session_columns:
            db.execute(text("ALTER TABLE userSession ADD COLUMN tokenHash VARCHAR(64)"))
        if "userAgent" not in session_columns:
            db.execute(text("ALTER TABLE userSession ADD COLUMN userAgent VARCHAR(300)"))
        if "lastSeenAt" not in session_columns:
            db.execute(text("ALTER TABLE userSession ADD COLUMN lastSeenAt VARCHAR(64)"))
        legacy_rows = db.execute(
            text("SELECT sessionId FROM userSession WHERE tokenHash IS NULL OR tokenHash = ''")
        ).all()
        for (session_id,) in legacy_rows:
            placeholder = hashlib.sha256(f"revoked-legacy-session:{session_id}".encode()).hexdigest()
            db.execute(
                text(
                    "UPDATE userSession SET tokenHash = :token_hash, "
                    "revokedAt = COALESCE(revokedAt, createdAt) WHERE sessionId = :session_id"
                ),
                {"token_hash": placeholder, "session_id": session_id},
            )
        db.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_userSession_tokenHash "
                "ON userSession(tokenHash)"
            )
        )
        db.commit()
    finally:
        db.close()
