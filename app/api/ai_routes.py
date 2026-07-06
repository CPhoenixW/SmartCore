from __future__ import annotations

import json
from typing import Any

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from app.config import get_settings
from app.new_core.models import nowIso

router = APIRouter(prefix="/api", tags=["api"])


class ParseBody(BaseModel):
    text: str
    scene: str = "create_event"
    now: str | None = None


def _strip_json_fence(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def _normalize_priority(value: Any, *, tab: str) -> str:
    text = str(value or "").strip().lower()
    if text in {"high", "高", "urgent", "important", "紧急", "重要"}:
        return "high"
    if text in {"low", "低", "later", "不急", "不重要"}:
        return "low"
    if text in {"mid", "middle", "medium", "normal", "普通", "中"}:
        return "mid"
    return "high" if tab == "ddl" else "mid"


def _normalize_parsed(data: dict[str, Any]) -> dict[str, Any]:
    raw_type = str(data.get("tab") or data.get("evtType") or data.get("type") or "plan").strip().lower()
    tab = "ddl" if raw_type in {"ddl", "deadline", "截止", "截止事项"} else "plan"
    normalized = {
        "tab": tab,
        "evtType": tab,
        "title": str(data.get("title") or "").strip(),
        "desc": str(data.get("desc") or data.get("description") or "").strip(),
        "prio": _normalize_priority(data.get("prio") or data.get("priority"), tab=tab),
        "durationMin": int(data.get("durationMin") or data.get("duration") or 30),
        "hardDdl": bool(data.get("hardDdl", False)),
    }
    if tab == "ddl":
        normalized["endTime"] = data.get("endTime") or data.get("deadline") or data.get("at")
    else:
        normalized["stTime"] = data.get("stTime") or data.get("startTime") or data.get("at")
    return normalized


@router.post("/llm/parse")
def parse_text(body: ParseBody) -> dict[str, Any]:
    settings = get_settings()
    parsed = None
    now = body.now or nowIso()
    if settings.deepseek_api_key:
        prompt = f"""
你是 SmartCore 的事件解析器。只返回一个 JSON 对象，不要 Markdown，不要解释。

当前时间：{now}
用户输入：{body.text}

目标事件只有两类：
1. plan：计划事项，有开始时间 stTime 和持续时间 durationMin。
2. ddl：截止事项，有截止时间 endTime。不要把 ddl 解析成 plan。

必须返回字段：
{{
  "tab": "plan" 或 "ddl",
  "evtType": "plan" 或 "ddl",
  "title": "去掉时间、我要、提醒我等语气词后的短标题",
  "desc": "必须生成一句中文描述，不允许为空；plan 描述包含时间段/持续时间和要做的事；ddl 描述包含截止时间和要完成的事",
  "prio": "low" 或 "mid" 或 "high",
  "stTime": "ISO8601，仅 plan 使用，否则 null",
  "endTime": "ISO8601，仅 ddl 使用，否则 null",
  "durationMin": 整数分钟，仅 plan 使用；未知默认 30,
  "hardDdl": 布尔值，仅 ddl 使用
}}

分类规则：
- “X点到Y点”“从X点到Y点”“X:00-Y:00”是 plan，stTime 为 X，durationMin 为 Y-X 的分钟数。
- “X点前”“X点之前”“截止到X点”“最晚X点”是 ddl，endTime 为 X。
- “提交/截止/到期/ddl/deadline”通常是 ddl。
- “看/学习/复习/开发/写/做/安排/计划”通常是 plan，除非出现“前/之前/截止/最晚”。
- 没有优先级词时，plan 默认 mid，ddl 默认 high。
- “紧急/重要/必须/一定”是 high；“不急/低优先级”是 low。
- 中文相对日期如今天、明天、后天必须结合当前时间转换为 ISO8601。
- 对于没有上午/下午/晚上修饰的“今天五点到十点”，按 17:00-22:00 理解；对于“今天十点前”，按 10:00 理解。
""".strip()
        payload = {
            "model": settings.llm_model,
            "messages": [
                {"role": "system", "content": "你只输出严格 JSON。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
        }
        headers = {"Authorization": "Bearer " + settings.deepseek_api_key, "Content-Type": "application/json"}
        try:
            resp = httpx.post(
                settings.deepseek_base_url.rstrip("/") + "/chat/completions",
                json=payload,
                headers=headers,
                timeout=12,
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"]
            data = json.loads(_strip_json_fence(str(raw)))
            if isinstance(data, dict):
                parsed = _normalize_parsed(data)
        except Exception:
            parsed = None
    return {"ok": True, "data": {"status": "ok" if parsed else "fallback", "scene": body.scene, "text": body.text, "parsed": parsed, "now": now}}
