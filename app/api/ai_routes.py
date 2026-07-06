from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["api"])


class ParseBody(BaseModel):
    text: str
    scene: str = "create_event"


@router.post("/llm/parse")
def parse_text(body: ParseBody) -> dict[str, Any]:
    return {"ok": True, "data": {"status": "fallback", "scene": body.scene, "text": body.text, "parsed": None}}
