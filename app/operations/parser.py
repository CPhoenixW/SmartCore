from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ParsedOperation:
    source: str
    raw_text: str
    action_name: str
    payload: dict
    confidence: float
    needs_confirmation: bool


class OperationParser:
    """Natural-language operation parser backed by an LLM provider."""

    def __init__(self, llm_parser: object) -> None:
        self._llm_parser = llm_parser

    def parse(
        self,
        text: str,
        *,
        source: str,
        now: datetime | None = None,
    ) -> ParsedOperation:
        return self._llm_parser.parse(text, source=source, now=now)

    def select_candidates(
        self,
        *,
        raw_text: str,
        parsed: ParsedOperation,
        candidates: list[dict],
    ) -> dict:
        if not hasattr(self._llm_parser, "select_candidates"):
            raise ValueError("candidate selection is not available")
        return self._llm_parser.select_candidates(
            raw_text=raw_text,
            parsed=parsed,
            candidates=candidates,
        )
