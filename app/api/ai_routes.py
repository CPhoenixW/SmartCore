from __future__ import annotations

import json
from typing import Any

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from app.config import get_settings

router = APIRouter(prefix="/api", tags=["api"])


class ParseBody(BaseModel):
    text: str
    scene: str = "create_event"


@router.post("/llm/parse")
def parse_text(body: ParseBody) -> dict[str, Any]:
    settings = get_settings()
    parsed = None
    if settings.deepseek_api_key:
        prompt = "只返回 JSON。字段：tab,title,desc,prio,at,hardDdl。用户输入：" + body.text
        payload = {"model": settings.llm_model, "messages": [{"role": "user", "content": prompt}]}
        headers = {"Authorization": "Bearer " + settings.deepseek_api_key, "Content-Type": "application/json"}
        try:
            resp = httpx.post(settings.deepseek_base_url.rstrip("/") + "/chat/completions", json=payload, headers=headers, timeout=20)
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"]
            raw = str(raw).strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            data = json.loads(raw)
            if isinstance(data, dict):
                parsed = data
        except Exception:
            parsed = None
    return {"ok": True, "data": {"status": "ok" if parsed else "fallback", "scene": body.scene, "text": body.text, "parsed": parsed}}
