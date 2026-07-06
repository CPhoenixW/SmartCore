from __future__ import annotations

import json
from typing import Any

import httpx

from app.config import get_settings


def parse_event_text(text: str, *, scene: str = "create_event") -> dict[str, Any] | None:
    settings = get_settings()
    token = settings.deepseek_api_key
    if not token:
        return None
    prompt = (
        "你是 SmartCore 的事件解析器。只返回 JSON，不要解释。"
        "字段：tab(life或ddl), title, desc, prio(high/mid/low), at(YYYY-MM-DDTHH:MM), hardDdl(boolean)。"
        f"场景：{scene}\n用户输入：{text}"
    )
    payload = {
        "model": settings.llm_model,
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        resp = httpx.post(
            settings.deepseek_base_url.rstrip("/") + "/chat/completions",
            json=payload,
            headers=headers,
            timeout=20,
        )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"]
    except Exception:
        return None
    raw = str(raw).strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None
