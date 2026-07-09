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


def _normalize_weekday(value: Any) -> int | None:
    aliases = {
        "monday": 1, "mon": 1, "星期一": 1, "周一": 1,
        "tuesday": 2, "tue": 2, "星期二": 2, "周二": 2,
        "wednesday": 3, "wed": 3, "星期三": 3, "周三": 3,
        "thursday": 4, "thu": 4, "星期四": 4, "周四": 4,
        "friday": 5, "fri": 5, "星期五": 5, "周五": 5,
        "saturday": 6, "sat": 6, "星期六": 6, "周六": 6,
        "sunday": 7, "sun": 7, "星期日": 7, "星期天": 7, "周日": 7,
    }
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in aliases:
        return aliases[text]
    try:
        number = int(text)
    except ValueError:
        return None
    return number if 1 <= number <= 7 else None


def _normalize_course(data: dict[str, Any]) -> dict[str, Any]:
    mode = str(data.get("weekMode") or data.get("week_mode") or "all").lower()
    if mode in {"每周", "weekly", "all"}:
        mode = "all"
    elif mode in {"单周", "odd"}:
        mode = "odd"
    elif mode in {"双周", "even"}:
        mode = "even"
    else:
        mode = "all"
    return {
        "tab": "course",
        "evtType": "course",
        "title": str(data.get("title") or data.get("courseName") or "").strip(),
        "courseName": str(data.get("courseName") or data.get("title") or "").strip(),
        "teacher": str(data.get("teacher") or "").strip() or None,
        "location": str(data.get("location") or data.get("room") or "").strip() or None,
        "semesterStart": data.get("semesterStart") or data.get("stDate") or data.get("startDate"),
        "weekDay": _normalize_weekday(data.get("weekDay") or data.get("weekday")),
        "stTime": data.get("stTime") or data.get("startTime"),
        "endTime": data.get("endTime") or data.get("finishTime"),
        "startWeek": int(data.get("startWeek") or 1),
        "endWeek": int(data.get("endWeek") or 16),
        "weekMode": mode,
        "desc": str(data.get("desc") or data.get("description") or "").strip(),
        "prio": _normalize_priority(data.get("prio") or data.get("priority"), tab="course"),
    }


def _normalize_event(data: dict[str, Any]) -> dict[str, Any]:
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


def _course_prompt(text: str, now: str) -> str:
    return f"""
你是 SmartCore 的课程表解析器。只返回严格 JSON，不要 Markdown，不要解释。
当前时间：{now}，时区 Asia/Shanghai。
用户输入：{text}

课程只使用一个学期开始日期，并按照周次、星期和上课时间计算所有实际日期。
必须输出：
{{
  "evtType": "course",
  "courseName": "课程名称",
  "title": "课程名称",
  "teacher": "教师或 null",
  "location": "教室或 null",
  "semesterStart": "YYYY-MM-DD 或 null",
  "weekDay": 1到7，星期一为1、星期日为7,
  "stTime": "HH:MM",
  "endTime": "HH:MM",
  "startWeek": 整数，默认1,
  "endWeek": 整数，默认16,
  "weekMode": "all"、"odd"或"even",
  "desc": "课程说明",
  "prio": "low"、"mid"或"high"
}}
规则：
- 不输出课程结束日期；由 semesterStart、startWeek、endWeek 和 weekDay 自动计算。
- 周一到周日严格对应 1 到 7。
- “每周”是 all，“单周”是 odd，“双周”是 even。
- 用户未提供起止周时，startWeek=1、endWeek=16。
- 缺少学期开始日期时 semesterStart=null，不要编造。
- 时间只输出 24 小时制 HH:MM。
""".strip()


def _event_prompt(text: str, now: str) -> str:
    return f"""
你是 SmartCore 的事件解析器。只返回一个 JSON 对象，不要 Markdown，不要解释。
当前时间：{now}
时间规则：时区为 Asia/Shanghai。所有完整日期时间必须使用带 +08:00 偏移量的 ISO8601。
用户输入：{text}
目标事件只有 plan 和 ddl。
必须返回 tab、evtType、title、desc、prio、stTime、endTime、durationMin、hardDdl。
“X点到Y点”是 plan；“X点前/截止/最晚”是 ddl。相对日期必须结合当前时间转换。
""".strip()


@router.post("/llm/parse")
def parse_text(body: ParseBody) -> dict[str, Any]:
    settings = get_settings()
    parsed = None
    now = body.now or nowIso()
    if settings.deepseek_api_key:
        is_course = body.scene in {"create_course", "course", "course_form"}
        prompt = _course_prompt(body.text, now) if is_course else _event_prompt(body.text, now)
        payload = {
            "model": settings.llm_model,
            "messages": [
                {"role": "system", "content": "你只输出严格 JSON。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
        }
        headers = {
            "Authorization": "Bearer " + settings.deepseek_api_key,
            "Content-Type": "application/json",
        }
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
                parsed = _normalize_course(data) if is_course else _normalize_event(data)
        except Exception:
            parsed = None
    return {
        "ok": True,
        "data": {
            "status": "ok" if parsed else "fallback",
            "scene": body.scene,
            "text": body.text,
            "parsed": parsed,
            "now": now,
        },
    }
