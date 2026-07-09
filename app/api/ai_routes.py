from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import get_settings
from app.llm import LLMConfigurationError, LLMGatewayError, complete_chat
from app.new_core.custom_reminders import normalize_extra_reminders
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


def _extract_json_object(raw: str) -> dict[str, Any]:
    text = _strip_json_fence(raw)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        return parsed

    start = text.find("{")
    if start < 0:
        raise ValueError("模型返回内容中没有 JSON 对象")

    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start : index + 1]
                parsed = json.loads(candidate)
                if not isinstance(parsed, dict):
                    raise ValueError("模型返回的 JSON 不是对象")
                return parsed
    raise ValueError("模型返回的 JSON 对象不完整")


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
        "monday": 1,
        "mon": 1,
        "星期一": 1,
        "周一": 1,
        "tuesday": 2,
        "tue": 2,
        "星期二": 2,
        "周二": 2,
        "wednesday": 3,
        "wed": 3,
        "星期三": 3,
        "周三": 3,
        "thursday": 4,
        "thu": 4,
        "星期四": 4,
        "周四": 4,
        "friday": 5,
        "fri": 5,
        "星期五": 5,
        "周五": 5,
        "saturday": 6,
        "sat": 6,
        "星期六": 6,
        "周六": 6,
        "sunday": 7,
        "sun": 7,
        "星期日": 7,
        "星期天": 7,
        "周日": 7,
    }
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in aliases:
        return aliases[text]
    match = re.search(r"\d+", text)
    if not match:
        return None
    number = int(match.group())
    return number if 1 <= number <= 7 else None


def _safe_int(value: Any, default: int) -> int:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return int(value)
    match = re.search(r"-?\d+", str(value))
    return int(match.group()) if match else default


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
        "semesterStart": data.get("semesterStart")
        or data.get("stDate")
        or data.get("startDate"),
        "weekDay": _normalize_weekday(data.get("weekDay") or data.get("weekday")),
        "stTime": data.get("stTime") or data.get("startTime"),
        "endTime": data.get("endTime") or data.get("finishTime"),
        "startWeek": max(1, _safe_int(data.get("startWeek"), 1)),
        "endWeek": max(1, _safe_int(data.get("endWeek"), 16)),
        "weekMode": mode,
        "desc": str(data.get("desc") or data.get("description") or "").strip(),
        "prio": _normalize_priority(
            data.get("prio") or data.get("priority"),
            tab="course",
        ),
    }


def _normalize_event(data: dict[str, Any]) -> dict[str, Any]:
    raw_type = str(
        data.get("tab") or data.get("evtType") or data.get("type") or "plan"
    ).strip().lower()
    tab = "ddl" if raw_type in {"ddl", "deadline", "截止", "截止事项"} else "plan"
    raw_reminders = data.get("extraReminders") or data.get("reminders") or []
    normalized = {
        "tab": tab,
        "evtType": tab,
        "title": str(data.get("title") or "").strip(),
        "desc": str(data.get("desc") or data.get("description") or "").strip(),
        "prio": _normalize_priority(data.get("prio") or data.get("priority"), tab=tab),
        "durationMin": max(1, _safe_int(data.get("durationMin") or data.get("duration"), 30)),
        "hardDdl": bool(data.get("hardDdl", False)),
        "extraReminders": normalize_extra_reminders(raw_reminders if isinstance(raw_reminders, list) else []),
    }
    if tab == "ddl":
        normalized["endTime"] = data.get("endTime") or data.get("deadline") or data.get("at")
        normalized["extraReminders"] = []
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
必须返回 tab、evtType、title、desc、prio、stTime、endTime、durationMin、hardDdl、extraReminders。
“X点到Y点”是 plan；“X点前/截止/最晚”是 ddl。相对日期必须结合当前时间转换。
每个 plan 已固定生成两个提醒：开始前 10 分钟、结束前 10 分钟。不要把这两个固定提醒写进 extraReminders。
只有用户明确要求额外提醒时，才输出 extraReminders，例如：
[
  {{"anchor": "start", "offsetMin": 30}},
  {{"anchor": "end", "offsetMin": 5}}
]
anchor 只能是 start 或 end；offsetMin 是提前分钟数。用户没有要求额外提醒时输出空数组。
ddl 的 extraReminders 必须为空数组。
""".strip()


@router.post("/llm/parse")
def parse_text(body: ParseBody) -> dict[str, Any]:
    settings = get_settings()
    now = body.now or nowIso()
    is_course = body.scene in {"create_course", "course", "course_form"}
    prompt = _course_prompt(body.text, now) if is_course else _event_prompt(body.text, now)

    try:
        raw = complete_chat(
            [
                {"role": "system", "content": "你只输出严格 JSON。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            settings=settings,
        )
        data = _extract_json_object(raw)
        parsed = _normalize_course(data) if is_course else _normalize_event(data)
    except LLMConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMGatewayError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=502,
            detail=f"模型返回内容无法解析：{exc}",
        ) from exc

    return {
        "ok": True,
        "data": {
            "status": "ok",
            "scene": body.scene,
            "text": body.text,
            "parsed": parsed,
            "now": now,
            "provider": settings.llm_provider,
            "model": settings.llm_model,
        },
    }
