from __future__ import annotations

from typing import Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.server.db.session import Base
from app.server.new_core import crud

_ALLOWED_REMINDER_CHANNELS = {"screen"}


class UserPreference(Base):
    __tablename__ = "userPreference"

    userId: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("appUser.userId", ondelete="CASCADE"),
        primary_key=True,
    )
    reminderChannel: Mapped[str] = mapped_column(
        String(20),
        default="screen",
        nullable=False,
    )


def _ensure_preference(db: Session, user_id: str = crud.DEFAULT_USER_ID) -> UserPreference:
    crud.getCurrentUser(db, userId=user_id)
    row = db.get(UserPreference, user_id)
    if row is None:
        row = UserPreference(userId=user_id, reminderChannel="screen")
        db.add(row)
        db.flush()
    return row


def get_user_preferences(
    db: Session,
    *,
    user_id: str = crud.DEFAULT_USER_ID,
) -> dict[str, Any]:
    row = _ensure_preference(db, user_id)
    if row.reminderChannel != "screen":
        row.reminderChannel = "screen"
    return {"reminderChannel": "screen"}


def update_user_preferences(
    db: Session,
    *,
    reminder_channel: str | None = None,
    user_id: str = crud.DEFAULT_USER_ID,
) -> dict[str, Any]:
    row = _ensure_preference(db, user_id)
    if reminder_channel is not None:
        normalized = reminder_channel.strip().lower()
        if normalized not in _ALLOWED_REMINDER_CHANNELS:
            raise ValueError("reminderChannel must be screen")
        row.reminderChannel = normalized
    db.commit()
    db.refresh(row)
    return {
        "reminderChannel": row.reminderChannel,
    }
