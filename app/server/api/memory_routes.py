from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.server.auth.security import require_authenticated_user_id
from app.server.config import Settings, get_settings
from app.server.db.session import get_db
from app.server.new_core.memory import (
    MEMORY_TYPES,
    TYPE_LABELS,
    create_memory,
    delete_memory,
    list_memories,
    memory_dict,
    update_memory,
)

router = APIRouter(prefix="/api/memory", tags=["memory"])


class MemoryCreateBody(BaseModel):
    content: str = Field(min_length=1, max_length=300)
    type: str | None = Field(default=None, max_length=20)
    expiresAt: str | None = Field(default=None, max_length=64)


class MemoryUpdateBody(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=300)
    type: str | None = Field(default=None, max_length=20)
    expiresAt: str | None = Field(default=None, max_length=64)
    clearExpiry: bool = False


def _error(exc: ValueError) -> HTTPException:
    detail = str(exc)
    return HTTPException(status_code=404 if "not found" in detail else 422, detail=detail)


def _check_type(value: str | None) -> None:
    if value is not None and value not in MEMORY_TYPES:
        raise HTTPException(status_code=422, detail="invalid memory type")


@router.get("")
def read_memories(
    includeExpired: bool = Query(default=False),
    user_id: str = Depends(require_authenticated_user_id),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    items = list_memories(db, user_id=user_id, include_expired=includeExpired)
    return {
        "ok": True,
        "data": {
            "enabled": settings.memory_enabled,
            "items": items,
            "types": [{"value": kind, "label": TYPE_LABELS[kind]} for kind in MEMORY_TYPES],
        },
    }


@router.post("")
def add_memory(
    body: MemoryCreateBody,
    user_id: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _check_type(body.type)
    try:
        row, created = create_memory(
            db,
            user_id=user_id,
            content=body.content,
            mem_type=body.type,
            source="user_explicit",
            confidence=1.0,
            expires_at=body.expiresAt,
        )
    except ValueError as exc:
        raise _error(exc) from exc
    return {"ok": True, "data": {**memory_dict(row), "created": created}}


@router.patch("/{memory_id}")
def edit_memory(
    memory_id: str,
    body: MemoryUpdateBody,
    user_id: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _check_type(body.type)
    try:
        row = update_memory(
            db,
            user_id=user_id,
            memory_id=memory_id,
            content=body.content,
            mem_type=body.type,
            expires_at=body.expiresAt,
            clear_expiry=body.clearExpiry,
        )
    except ValueError as exc:
        raise _error(exc) from exc
    return {"ok": True, "data": memory_dict(row)}


@router.delete("/{memory_id}")
def remove_memory(
    memory_id: str,
    user_id: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        row = delete_memory(db, user_id=user_id, memory_id=memory_id)
    except ValueError as exc:
        raise _error(exc) from exc
    return {"ok": True, "data": {"memoryId": row.memoryId, "deleted": True}}
