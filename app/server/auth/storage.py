from __future__ import annotations

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
            db.commit()
    finally:
        db.close()
