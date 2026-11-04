"""Owner-scoped long-term personal memory (D024).

Short-term context stays in :func:`assistant_history.recent_context_messages`.
This module stores a small set of durable facts about the user, injects the
most relevant ones into every assistant turn, and merges new facts extracted
after a turn completes. Every function takes a verified ``user_id``; callers
must never pass a client-supplied owner.
"""

from __future__ import annotations

import json
import logging
import math
import re
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.server.config import Settings, get_settings
from app.server.new_core.models import UserMemory, nowIso

logger = logging.getLogger(__name__)

MEMORY_TYPES = ("profile", "preference", "habit", "goal", "relationship", "fact")
MEMORY_SOURCES = ("auto_extracted", "user_explicit")
TYPE_LABELS = {
    "profile": "个人信息",
    "preference": "偏好",
    "habit": "习惯",
    "goal": "目标",
    "relationship": "关系",
    "fact": "事实",
}
MAX_CONTENT_CHARS = 120
MAX_OPERATIONS_PER_TURN = 6
MIN_AUTO_CONFIDENCE = 0.5
DUPLICATE_SIMILARITY = 0.72
FORGET_SIMILARITY = 0.45
_DEFAULT_TZ = ZoneInfo("Asia/Shanghai")

_SECRET_PATTERN = re.compile(
    r"(密码|口令|密钥|私钥|验证码|银行卡|信用卡|身份证号|社保号|护照号|cvv|password|passwd|"
    r"api[ _-]?key|access[ _-]?token|secret|sk-[A-Za-z0-9]{8,}|\b\d{15,19}\b)",
    re.IGNORECASE,
)
_REMEMBER_PATTERN = re.compile(
    r"^\s*(?:请|麻烦)?你?(?:帮我)?(?:要)?(?:记住|牢记)(?:一下|这个|这件事|这点)?[:：,，、\s]*(?P<body>.+)$",
    re.S,
)
_FORGET_PATTERN = re.compile(
    r"^\s*(?:请|麻烦)?你?(?:帮我)?(?:忘掉|忘了吧|别再记住|不用再记住|不要再记住|删除记忆|删掉记忆|删掉这条记忆)"
    r"(?:一下|关于)?[:：,，、\s]*(?P<body>.*)$",
    re.S,
)
# "记住明天三点开会" is a reminder, not a personal fact: leave it to the
# scheduling tools so the user's existing workflow keeps working.
_SCHEDULE_PATTERN = re.compile(
    r"(今天|明天|后天|今晚|明早|明晚|下周|本周|这周|下个月|周[一二三四五六日天]|星期[一二三四五六日天]|"
    r"\d+\s*[点:：时]|\d+\s*月\s*\d+|\d+\s*号|提醒我|截止|ddl)",
    re.IGNORECASE,
)
_CHITCHAT_PATTERN = re.compile(
    r"^\s*(你好|您好|hi|hello|嗨|在吗|谢谢|多谢|好的|好|嗯+|哦+|ok|okay|收到|行|可以|没事|晚安|早安|早上好|拜拜)[!！。.~～\s]*$",
    re.IGNORECASE,
)
_PUNCTUATION = re.compile(r"[\s,，。.!！?？;；:：、\"'“”‘’()（）\[\]【】<>《》~～-]+")


@dataclass
class MemoryCommandResult:
    action: str
    memories: list[dict[str, Any]] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if self.action == "remember":
            return "已写入长期记忆：" + "；".join(item["content"] for item in self.memories)
        if self.memories:
            return "已从长期记忆删除：" + "；".join(item["content"] for item in self.memories)
        return "长期记忆中没有找到要忘掉的内容。"


# ---------------------------------------------------------------------------
# Text helpers


def _now() -> datetime:
    return datetime.now(_DEFAULT_TZ)


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_DEFAULT_TZ)
    return parsed


def normalize_expires_at(value: str | None) -> str | None:
    if value is None or not str(value).strip():
        return None
    parsed = _parse_time(str(value))
    if parsed is None:
        raise ValueError("expiresAt must be an ISO 8601 time")
    return parsed.isoformat()


def contains_secret(text: str) -> bool:
    return bool(_SECRET_PATTERN.search(text or ""))


def normalize_content(text: str) -> str:
    content = re.sub(r"\s+", " ", str(text or "")).strip()
    content = content.strip("。.!！~～ ")
    if content.startswith("我的"):
        content = "用户的" + content[2:]
    elif content.startswith("我"):
        content = "用户" + content[1:]
    return content[:MAX_CONTENT_CHARS]


def _comparable(text: str) -> str:
    value = _PUNCTUATION.sub("", str(text or "").lower())
    for prefix in ("用户的", "用户", "我的", "我"):
        if value.startswith(prefix):
            value = value[len(prefix):]
            break
    return value


def _bigrams(text: str) -> set[str]:
    value = _comparable(text)
    if len(value) < 2:
        return {value} if value else set()
    return {value[index:index + 2] for index in range(len(value) - 1)}


def similarity(left: str, right: str) -> float:
    a, b = _bigrams(left), _bigrams(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _containment(needle: str, haystack: str) -> float:
    a, b = _bigrams(needle), _bigrams(haystack)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a)


def guess_type(content: str) -> str:
    text = content or ""
    if re.search(r"(朋友|同学|老师|导师|老板|同事|室友|妈妈|爸爸|父母|女朋友|男朋友|对象|老婆|老公|孩子|家人)", text):
        return "relationship"
    if re.search(r"(目标|想要|打算|计划在|希望|准备考|要考|争取)", text):
        return "goal"
    if re.search(r"(习惯|每天|通常|一般会|总是|经常|每周|每晚|每早)", text):
        return "habit"
    if re.search(r"(喜欢|不喜欢|讨厌|偏好|倾向|更愿意|爱吃|不吃|希望你|别给我|不要给我)", text):
        return "preference"
    if re.search(r"(我是|我叫|名字|专业|学校|大学|工作|职业|住在|年级|研究生|本科|博士|生日)", text):
        return "profile"
    return "fact"


def _clean_type(value: Any, content: str) -> str:
    candidate = str(value or "").strip().lower()
    return candidate if candidate in MEMORY_TYPES else guess_type(content)


# ---------------------------------------------------------------------------
# Storage


def memory_dict(row: UserMemory) -> dict[str, Any]:
    return {
        "memoryId": row.memoryId,
        "type": row.memType,
        "typeLabel": TYPE_LABELS.get(row.memType, row.memType),
        "content": row.content,
        "source": row.source,
        "confidence": round(float(row.confidence or 0), 2),
        "createdAt": row.createdAt,
        "updatedAt": row.updatedAt,
        "lastUsedAt": row.lastUsedAt,
        "expiresAt": row.expiresAt,
    }


def _is_active(row: UserMemory, now: datetime | None = None) -> bool:
    if row.deletedAt:
        return False
    expires = _parse_time(row.expiresAt)
    return expires is None or expires > (now or _now())


def active_memories(db: Session, *, user_id: str) -> list[UserMemory]:
    rows = db.scalars(
        select(UserMemory)
        .where(UserMemory.userId == user_id, UserMemory.deletedAt.is_(None))
        .order_by(UserMemory.updatedAt.desc(), UserMemory.memoryId.desc())
    ).all()
    now = _now()
    return [row for row in rows if _is_active(row, now)]


def list_memories(db: Session, *, user_id: str, include_expired: bool = False) -> list[dict[str, Any]]:
    if include_expired:
        rows = db.scalars(
            select(UserMemory)
            .where(UserMemory.userId == user_id, UserMemory.deletedAt.is_(None))
            .order_by(UserMemory.updatedAt.desc(), UserMemory.memoryId.desc())
        ).all()
    else:
        rows = active_memories(db, user_id=user_id)
    return [memory_dict(row) for row in rows]


def _owned(db: Session, *, user_id: str, memory_id: str) -> UserMemory:
    row = db.get(UserMemory, memory_id)
    if row is None or row.userId != user_id or row.deletedAt:
        raise ValueError("memory not found")
    return row


def _validate_content(content: str) -> str:
    clean = normalize_content(content)
    if len(_comparable(clean)) < 2:
        raise ValueError("memory content is too short")
    if contains_secret(clean):
        raise ValueError("memory content looks like a secret and was not saved")
    return clean


def _find_duplicate(rows: Iterable[UserMemory], content: str) -> UserMemory | None:
    best: tuple[float, UserMemory] | None = None
    for row in rows:
        score = similarity(row.content, content)
        if score >= DUPLICATE_SIMILARITY and (best is None or score > best[0]):
            best = (score, row)
    return best[1] if best else None


def _enforce_cap(db: Session, *, user_id: str, max_active: int) -> None:
    rows = active_memories(db, user_id=user_id)
    overflow = len(rows) - max(1, max_active)
    if overflow <= 0:
        return
    # Evict the least valuable automatic memories first; explicit ones are
    # only evicted when nothing automatic is left.
    ranked = sorted(
        rows,
        key=lambda row: (
            row.source == "user_explicit",
            float(row.confidence or 0),
            row.lastUsedAt or row.updatedAt,
        ),
    )
    now = nowIso()
    for row in ranked[:overflow]:
        row.deletedAt = now
        row.updatedAt = now


def create_memory(
    db: Session,
    *,
    user_id: str,
    content: str,
    mem_type: str | None = None,
    source: str = "user_explicit",
    confidence: float | None = None,
    expires_at: str | None = None,
    max_active: int | None = None,
    commit: bool = True,
) -> tuple[UserMemory, bool]:
    """Insert a memory or merge it into a near-duplicate. Returns (row, created)."""

    if source not in MEMORY_SOURCES:
        raise ValueError("invalid memory source")
    clean = _validate_content(content)
    kind = _clean_type(mem_type, clean)
    level = float(confidence if confidence is not None else (1.0 if source == "user_explicit" else 0.7))
    level = max(0.0, min(1.0, level))
    expires = normalize_expires_at(expires_at)
    now = nowIso()
    duplicate = _find_duplicate(active_memories(db, user_id=user_id), clean)
    if duplicate is not None:
        duplicate.content = clean
        duplicate.memType = kind if mem_type else duplicate.memType
        duplicate.confidence = max(float(duplicate.confidence or 0), level)
        if source == "user_explicit":
            duplicate.source = "user_explicit"
        duplicate.expiresAt = expires
        duplicate.updatedAt = now
        row, created = duplicate, False
    else:
        row = UserMemory(
            userId=user_id,
            memType=kind,
            content=clean,
            source=source,
            confidence=level,
            createdAt=now,
            updatedAt=now,
            expiresAt=expires,
        )
        db.add(row)
        db.flush()
        created = True
    _enforce_cap(db, user_id=user_id, max_active=max_active or get_settings().memory_max_active)
    if commit:
        db.commit()
        db.refresh(row)
    return row, created


def update_memory(
    db: Session,
    *,
    user_id: str,
    memory_id: str,
    content: str | None = None,
    mem_type: str | None = None,
    expires_at: str | None = None,
    clear_expiry: bool = False,
    commit: bool = True,
) -> UserMemory:
    row = _owned(db, user_id=user_id, memory_id=memory_id)
    if content is not None:
        row.content = _validate_content(content)
    if mem_type is not None:
        if mem_type not in MEMORY_TYPES:
            raise ValueError("invalid memory type")
        row.memType = mem_type
    if clear_expiry:
        row.expiresAt = None
    elif expires_at is not None:
        row.expiresAt = normalize_expires_at(expires_at)
    row.updatedAt = nowIso()
    if commit:
        db.commit()
        db.refresh(row)
    return row


def delete_memory(db: Session, *, user_id: str, memory_id: str, commit: bool = True) -> UserMemory:
    row = _owned(db, user_id=user_id, memory_id=memory_id)
    now = nowIso()
    row.deletedAt = now
    row.updatedAt = now
    if commit:
        db.commit()
    return row


def forget_matching(db: Session, *, user_id: str, text: str, commit: bool = True) -> list[UserMemory]:
    target = normalize_content(text)
    if len(_comparable(target)) < 2:
        return []
    matched: list[UserMemory] = []
    for row in active_memories(db, user_id=user_id):
        score = max(
            similarity(row.content, target),
            _containment(target, row.content),
            _containment(row.content, target),
        )
        if score >= FORGET_SIMILARITY or _comparable(target) in _comparable(row.content):
            matched.append(row)
    now = nowIso()
    for row in matched:
        row.deletedAt = now
        row.updatedAt = now
    if commit:
        db.commit()
    return matched


# ---------------------------------------------------------------------------
# Prompt injection


def _recency_score(row: UserMemory, now: datetime) -> float:
    updated = _parse_time(row.lastUsedAt or row.updatedAt) or now
    days = max(0.0, (now - updated).total_seconds() / 86400)
    return math.exp(-days / 30)


def select_for_prompt(
    db: Session,
    *,
    user_id: str,
    query_text: str,
    limit: int = 16,
    max_chars: int = 1500,
    mark_used: bool = True,
) -> list[str]:
    """Return compact 'about the user' lines for the current turn.

    Relevance is a cheap character-bigram overlap with the current message;
    explicit, confident and recently used memories break ties. The caller owns
    the transaction; this only flushes ``lastUsedAt`` updates.
    """

    rows = active_memories(db, user_id=user_id)
    if not rows:
        return []
    now = _now()
    query = query_text or ""

    def score(row: UserMemory) -> float:
        relevance = _containment(row.content, query) + similarity(row.content, query)
        return (
            2.0 * relevance
            + 0.6 * float(row.confidence or 0)
            + (0.3 if row.source == "user_explicit" else 0.0)
            + 0.4 * _recency_score(row, now)
        )

    ranked = sorted(rows, key=score, reverse=True)[: max(1, min(limit, 40))]
    order = {kind: index for index, kind in enumerate(MEMORY_TYPES)}
    ranked.sort(key=lambda row: order.get(row.memType, 99))
    lines: list[str] = []
    used_rows: list[UserMemory] = []
    used = 0
    for row in ranked:
        line = f"[{TYPE_LABELS.get(row.memType, row.memType)}] {row.content}"
        if used + len(line) > max_chars:
            continue
        lines.append(line)
        used_rows.append(row)
        used += len(line) + 1
    if mark_used and used_rows:
        stamp = nowIso()
        for row in used_rows:
            row.lastUsedAt = stamp
        db.flush()
    return lines


# ---------------------------------------------------------------------------
# Explicit commands


def parse_explicit_command(text: str) -> tuple[str, str] | None:
    raw = str(text or "").strip()
    if not raw or len(raw) > 400:
        return None
    forget = _FORGET_PATTERN.match(raw)
    if forget:
        return ("forget", forget.group("body").strip())
    remember = _REMEMBER_PATTERN.match(raw)
    if remember:
        body = remember.group("body").strip()
        if not body or _SCHEDULE_PATTERN.search(body):
            return None
        return ("remember", body)
    return None


def handle_explicit_command(db: Session, *, user_id: str, text: str) -> MemoryCommandResult | None:
    command = parse_explicit_command(text)
    if command is None:
        return None
    action, body = command
    if action == "forget":
        rows = forget_matching(db, user_id=user_id, text=body, commit=False)
        db.commit()
        return MemoryCommandResult("forget", [memory_dict(row) for row in rows])
    if contains_secret(body):
        return None
    try:
        row, _created = create_memory(
            db, user_id=user_id, content=body, source="user_explicit", confidence=1.0
        )
    except ValueError:
        return None
    return MemoryCommandResult("remember", [memory_dict(row)])


# ---------------------------------------------------------------------------
# Post-turn extraction

EXTRACTION_PROMPT = """你是 SmartCore 个人助手的长期记忆整理器。
根据最新一轮对话，判断是否出现了值得长期记住的、关于用户本人的稳定信息：
profile 个人信息、preference 偏好、habit 习惯、goal 目标、relationship 重要关系、fact 其他长期事实。

必须忽略：寒暄闲聊；一次性的日程、待办、提醒、DDL（已由日程系统管理）；临时状态或情绪；
助手自己的推测；任何密码、密钥、token、验证码、证件号、银行卡号等敏感信息。

与已有记忆比较后输出操作：
- ADD：全新的长期信息。
- UPDATE：修正或补充已有记忆，给出该记忆的 id 和完整的新内容。
- DELETE：用户否认、不再成立或要求忘掉某条记忆，给出 id。
- 没有变化就不输出操作。
每条 content 是一句不超过 60 字的简短中文，用“用户”指代用户。
有明确时效的信息可给 expiresAt（带时区 ISO 8601），否则为 null。
只输出 JSON：{"operations":[{"op":"ADD|UPDATE|DELETE","id":"已有记忆id或null","type":"profile|preference|habit|goal|relationship|fact","content":"...","confidence":0.0-1.0,"expiresAt":null}]}
没有可记的内容时输出 {"operations":[]}。"""


def should_extract(user_text: str) -> bool:
    text = str(user_text or "").strip()
    if len(text) < 4 or _CHITCHAT_PATTERN.match(text):
        return False
    return parse_explicit_command(text) is None


def _parse_operations(raw: str) -> list[dict[str, Any]]:
    text = str(raw or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return []
    try:
        payload = json.loads(text[start:end + 1])
    except ValueError:
        return []
    operations = payload.get("operations") if isinstance(payload, dict) else None
    if not isinstance(operations, list):
        return []
    return [item for item in operations if isinstance(item, dict)][:MAX_OPERATIONS_PER_TURN]


def apply_operations(
    db: Session,
    *,
    user_id: str,
    operations: list[dict[str, Any]],
    max_active: int,
) -> dict[str, int]:
    """Merge model-proposed operations. Invalid or unsafe ones are skipped."""

    counts = {"added": 0, "updated": 0, "deleted": 0, "skipped": 0}
    for op in operations[:MAX_OPERATIONS_PER_TURN]:
        action = str(op.get("op") or "").strip().upper()
        memory_id = str(op.get("id") or "").strip()
        content = str(op.get("content") or "").strip()
        try:
            confidence = float(op.get("confidence") if op.get("confidence") is not None else 0.7)
        except (TypeError, ValueError):
            confidence = 0.7
        try:
            if action == "DELETE" and memory_id:
                row = _owned(db, user_id=user_id, memory_id=memory_id)
                if row.source == "user_explicit" and confidence < 0.8:
                    counts["skipped"] += 1
                    continue
                delete_memory(db, user_id=user_id, memory_id=memory_id, commit=False)
                counts["deleted"] += 1
            elif action == "UPDATE" and memory_id and content:
                row = _owned(db, user_id=user_id, memory_id=memory_id)
                row.content = _validate_content(content)
                row.memType = _clean_type(op.get("type"), row.content)
                row.confidence = max(0.0, min(1.0, confidence))
                row.expiresAt = normalize_expires_at(op.get("expiresAt"))
                row.updatedAt = nowIso()
                counts["updated"] += 1
            elif action == "ADD" and content:
                if confidence < MIN_AUTO_CONFIDENCE:
                    counts["skipped"] += 1
                    continue
                _row, created = create_memory(
                    db,
                    user_id=user_id,
                    content=content,
                    mem_type=op.get("type"),
                    source="auto_extracted",
                    confidence=confidence,
                    expires_at=op.get("expiresAt"),
                    max_active=max_active,
                    commit=False,
                )
                counts["added" if created else "updated"] += 1
            else:
                counts["skipped"] += 1
        except ValueError:
            counts["skipped"] += 1
    db.commit()
    return counts


def extract_and_merge(
    db: Session,
    *,
    user_id: str,
    user_text: str,
    assistant_text: str,
    settings: Settings | None = None,
    llm: Callable[..., str] | None = None,
) -> dict[str, int] | None:
    active_settings = settings or get_settings()
    if not active_settings.memory_enabled or not should_extract(user_text):
        return None
    if llm is None:
        from app.server.llm.gateway import complete_chat

        llm = complete_chat
    existing = select_for_prompt_rows(db, user_id=user_id, query_text=user_text, limit=40)
    payload = {
        "existingMemories": [
            {"id": row.memoryId, "type": row.memType, "content": row.content} for row in existing
        ],
        "latestExchange": {
            "user": str(user_text or "")[:2000],
            "assistant": str(assistant_text or "")[:1500],
        },
    }
    raw = llm(
        [
            {"role": "system", "content": EXTRACTION_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        temperature=0,
        settings=active_settings,
        model=active_settings.memory_extraction_model or None,
        max_tokens=1200,
        response_format={"type": "json_object"},
        usage_label="memory_extraction",
    )
    operations = _parse_operations(raw)
    if not operations:
        return {"added": 0, "updated": 0, "deleted": 0, "skipped": 0}
    return apply_operations(
        db, user_id=user_id, operations=operations, max_active=active_settings.memory_max_active
    )


def select_for_prompt_rows(db: Session, *, user_id: str, query_text: str, limit: int) -> list[UserMemory]:
    rows = active_memories(db, user_id=user_id)
    rows.sort(
        key=lambda row: similarity(row.content, query_text) + _containment(row.content, query_text),
        reverse=True,
    )
    return rows[:limit]


_executor: ThreadPoolExecutor | None = None


def _extraction_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="smartcore-memory")
    return _executor


def _run_extraction(user_id: str, user_text: str, assistant_text: str) -> None:
    from app.server.db.session import SessionLocal

    db = SessionLocal()
    try:
        result = extract_and_merge(
            db, user_id=user_id, user_text=user_text, assistant_text=assistant_text
        )
        if result:
            logger.info("memory_extraction user=%s result=%s", user_id, result)
    except Exception:  # noqa: BLE001 - extraction must never affect the chat
        db.rollback()
        logger.warning("memory extraction failed for user=%s", user_id, exc_info=True)
    finally:
        db.close()


def schedule_extraction(
    *,
    user_id: str,
    user_text: str,
    assistant_text: str,
    settings: Settings | None = None,
) -> bool:
    """Queue a non-blocking extraction after a completed assistant turn."""

    active_settings = settings or get_settings()
    if not active_settings.memory_enabled or not should_extract(user_text):
        return False
    if not (active_settings.llm_api_key or active_settings.deepseek_api_key).strip():
        return False
    if not str(assistant_text or "").strip():
        return False
    try:
        _extraction_executor().submit(_run_extraction, user_id, user_text, assistant_text)
    except RuntimeError:
        return False
    return True
