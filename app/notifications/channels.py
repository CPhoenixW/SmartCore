from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class NotificationSendResult:
    success: bool
    external_message_id: str | None = None
    error_message: str | None = None


class NotificationChannel(Protocol):
    def send(self, *, target: str, title: str, content: str) -> NotificationSendResult: ...
