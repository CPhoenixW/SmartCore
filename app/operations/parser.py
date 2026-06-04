from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from app.feishu.commands import DATE_PATTERN

_ASSIGNMENT_PREFIX = "添加作业"


@dataclass(frozen=True)
class ParsedOperation:
    source: str
    raw_text: str
    action_name: str
    payload: dict
    confidence: float
    needs_confirmation: bool


class RuleBasedOperationParser:
    def __init__(self, *, tz: ZoneInfo) -> None:
        self._tz = tz

    def parse(self, text: str, *, source: str) -> ParsedOperation:
        normalized = text.strip()
        if normalized.startswith(_ASSIGNMENT_PREFIX):
            args = normalized.removeprefix(_ASSIGNMENT_PREFIX).strip()
            title, due_at = self._parse_assignment_args(args)
            fields: dict[str, str] = {"title": title}
            if due_at is not None:
                fields["due_at"] = due_at.isoformat()
            return ParsedOperation(
                source=source,
                raw_text=text,
                action_name="create_assignment",
                payload={"resource": "assignment", "fields": fields},
                confidence=0.95,
                needs_confirmation=True,
            )
        raise ValueError(f"unsupported operation text: {text!r}")

    def _parse_assignment_args(self, args: str) -> tuple[str, datetime | None]:
        match = DATE_PATTERN.match(args.strip())
        if not match:
            return args.strip(), None
        title = match.group("title").strip()
        raw_date = match.group("date").replace("T", " ")
        if len(raw_date) == 10:
            due_at = datetime.strptime(raw_date, "%Y-%m-%d").replace(tzinfo=self._tz)
        else:
            due_at = datetime.strptime(raw_date, "%Y-%m-%d %H:%M").replace(tzinfo=self._tz)
        return title, due_at
