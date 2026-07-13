from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import get_settings
from app.llm import LLMConfigurationError, LLMGatewayError, complete_chat
from app.new_core.ddl_service import default_ddl_plans
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
    if value in (None, "") or isinstance(value, bool):
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
        "semesterStart": data.get("semesterStart") or data.get("stDate") or data.get("startDate"),
        "weekDay": _normalize_weekday(data.get("weekDay") or data.get("weekday")),
        "stTime": data.get("stTime") or data.get("startTime"),
        "endTime": data.get("endTime") or data.get("finishTime"),
        "startWeek": max(1, _safe_int(data.get("startWeek"), 1)),
        "endWeek": max(1, _safe_int(data.get("endWeek"), 16)),
        "weekMode": mode,
        "desc": str(data.get("desc") or data.get("description") or "").strip(),
        "prio": _normalize_priority(data.get("prio") or data.get("priority"), tab="course"),
    }


def _event_type(data: dict[str, Any]) -> str:
    raw = str(data.get("tab") or data.get("evtType") or data.get("type") or "plan").strip().lower()
    if raw in {"ddl", "deadline", "截止", "截止事项"}:
        return "ddl"
    if raw in {"remind", "reminder", "提醒", "提醒事项"}:
        return "remind"
    return "plan"


def _normalize_ddl_plans(data: dict[str, Any], end_time: Any) -> list[dict[str, Any]]:
    raw_plans = data.get("plans") or data.get("linkedPlans")
    if not isinstance(raw_plans, list) or not raw_plans:
        if not end_time:
            return []
        return default_ddl_plans(str(end_time))
    result: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_plans):
        if not isinstance(raw, dict):
            continue
        role = str(raw.get("planRole") or raw.get("role") or "manual")
        if role not in {"one_day_before", "one_hour_before", "manual"}:
            role = "manual"
        st_time = raw.get("stTime") or raw.get("startTime") or raw.get("at")
        if not st_time:
            continue
        result.append(
            {
                "planRole": role,
                "title": str(raw.get("title") or "").strip() or None,
                "stTime": st_time,
                "durationMin": max(1, _safe_int(raw.get("durationMin") or raw.get("duration"), 30)),
                "sortOrder": index,
            }
        )
    return result


def _normalize_event(data: dict[str, Any]) -> dict[str, Any]:
    tab = _event_type(data)
    normalized = {
        "tab": tab,
        "evtType": tab,
        "title": str(data.get("title") or "").strip(),
        "desc": str(data.get("desc") or data.get("description") or "").strip(),
        "prio": _normalize_priority(data.get("prio") or data.get("priority"), tab=tab),
    }
    if tab == "ddl":
        end_time = data.get("endTime") or data.get("deadline") or data.get("at")
        normalized.update(
            {
                "endTime": end_time,
                "hardDdl": bool(data.get("hardDdl", False)),
                "plans": _normalize_ddl_plans(data, end_time),
            }
        )
    elif tab == "remind":
        normalized["triggerTime"] = data.get("triggerTime") or data.get("remindAt") or data.get("at")
    else:
        normalized.update(
            {
                "stTime": data.get("stTime") or data.get("startTime") or data.get("at"),
                "durationMin": max(1, _safe_int(data.get("durationMin") or data.get("duration"), 30)),
            }
        )
    return normalized


def _important_date_fallback(text: str) -> dict[str, Any] | None:
    """Keep important date-only reminders useful when the model output is malformed."""
    match = re.search(r"(?P<year>20\d{2})\s*年\s*(?P<month>\d{1,2})\s*月\s*(?P<day>\d{1,2})\s*(?:日|号)?", text)
    if match is None or not re.search(r"生日|纪念日|周年|千万不能忘|别忘", text):
        return None
    year, month, day = (int(match.group(name)) for name in ("year", "month", "day"))
    try:
        date_text = f"{year:04d}-{month:02d}-{day:02d}T09:00:00+08:00"
        # Validate calendar dates without changing the user-facing ISO value.
        datetime(year, month, day)
    except ValueError:
        return None
    subject = re.search(r"(.{1,24}?)(?:在)?\s*20\d{2}\s*年", text)
    title = "重要日期提醒"
    if subject:
        name = subject.group(1).strip(" ，,。！!：:")
        if name:
            title = f"{name}生日礼物" if "生日" in text and "生日" not in name else name
    return {
        "tab": "ddl",
        "evtType": "ddl",
        "title": title,
        "desc": text.strip(),
        "prio": "high",
        "endTime": date_text,
        "hardDdl": True,
        "plans": default_ddl_plans(date_text),
    }


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
当前时间：{now}，时区 Asia/Shanghai。
用户输入：{text}

事件类型只有：
- plan：有开始时间和持续时长的计划；系统会自动生成开始前10分钟、结束前10分钟两个提醒，不输出提醒记录。
- remind：单独提醒，只在 triggerTime 触发，不属于任何 plan。
- ddl：截止事项，可以关联多个 plan。

所有完整日期时间必须使用带 +08:00 偏移量的 ISO8601。
必须根据类型输出：
1. plan：evtType、title、desc、prio、stTime、durationMin。
2. remind：evtType、title、desc、prio、triggerTime。
3. ddl：evtType、title、desc、prio、endTime、hardDdl、plans。

DDL 的 plans 是数组，每项格式：
{{
  "planRole": "one_day_before"、"one_hour_before"或"manual",
  "title": "计划标题或 null",
  "stTime": "ISO8601",
  "durationMin": 分钟数
}}
如果用户没有特别说明 DDL 安排，默认生成两个计划：截止前一天安排30分钟、截止前一小时安排30分钟。
如果用户明确提出更多安排，可以输出多个 manual 计划。
分类规则（必须遵守）：
- “提醒我……”且没有持续时长，通常解析为 remind；“从X点做Y分钟”解析为 plan；“截止、最晚、提交”解析为 ddl。
- 生日、纪念日、约会、缴费、考试等带有明确日期且需要事先准备的事项，解析为 ddl；例如“依依宝宝2026年8月28号过生日，千万不能忘了给她准备礼物”必须是高优先级 ddl，title 为“依依宝宝生日礼物”，desc 保留原意，hardDdl=true。
- 用户仅给出年月日、没有时分时，使用当天 09:00:00+08:00；不得编造日期，只有明确表达“今天/明天/下周”等相对日期时才根据当前时间换算。
- “千万不能忘、务必、必须、重要”对应 prio=high；“可以、以后、有空”对应 prio=low。
- 输出前检查：title 非空；每个时间字段均为带 +08:00 的 ISO8601；ddl 必须有 endTime 和 hardDdl，plan 必须有 stTime 和 durationMin，remind 必须有 triggerTime。
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
        if not is_course and (not parsed["title"] or not (parsed.get("endTime") or parsed.get("stTime") or parsed.get("triggerTime"))):
            fallback = _important_date_fallback(body.text)
            if fallback is not None:
                parsed = fallback
    except LLMConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMGatewayError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (ValueError, json.JSONDecodeError) as exc:
        fallback = None if is_course else _important_date_fallback(body.text)
        if fallback is None:
            raise HTTPException(status_code=502, detail=f"模型返回内容无法解析：{exc}") from exc
        parsed = fallback

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
