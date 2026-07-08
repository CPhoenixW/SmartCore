from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.feishu.cards import build_reminder_card
from app.feishu.client import FeishuAPIError, FeishuClient
from app.new_core import crud
from app.new_core.preferences import get_user_preferences
from app.screen.manager import screenManager

_feishuClient: FeishuClient | None = None


def _getFeishuClient() -> FeishuClient | None:
    settings = get_settings()
    if not settings.feishu_app_id or not settings.feishu_app_secret:
        return None
    global _feishuClient
    if _feishuClient is None:
        _feishuClient = FeishuClient(settings.feishu_app_id, settings.feishu_app_secret)
    return _feishuClient


def buildReminderCard(*, evtId: str, title: str, content: str) -> dict[str, Any]:
    return build_reminder_card(
        evt_id=evtId,
        title=title,
        content=content,
        allow_done=True,
        allow_snooze=True,
    )


def _sendScreen(
    title: str,
    content: str,
    *,
    evtId: str | None = None,
    phase: str = "end",
) -> tuple[bool, str | None]:
    if phase == "start":
        message: dict[str, Any] = {
            "kind": "reminderSound",
            "title": title,
            "content": content,
        }
    else:
        message = {
            "kind": "reminder",
            "title": title,
            "content": content,
        }
        if evtId:
            message["evtId"] = evtId
    ok = screenManager.broadcastFromThread(message)
    return ok, None if ok else "screen websocket offline"


def _sendFeishuText(title: str, content: str) -> tuple[bool, str | None, str | None]:
    settings = get_settings()
    receive_id = settings.feishu_default_chat_id
    if not receive_id:
        return False, None, "FEISHU_DEFAULT_CHAT_ID not configured"
    client = _getFeishuClient()
    if client is None:
        return False, receive_id, "feishu app credentials not configured"
    try:
        client.send_text(receive_id, f"{title}\n{content}".strip())
    except FeishuAPIError as exc:
        return False, receive_id, str(exc)
    return True, receive_id, None


def _sendFeishu(title: str, content: str) -> tuple[bool, str | None, str | None]:
    return _sendFeishuText(title, content)


_baselineSendFeishu = _sendFeishu


def _sendFeishuReminderCard(
    *,
    evtId: str,
    title: str,
    content: str,
) -> tuple[bool, str | None, str | None]:
    settings = get_settings()
    receive_id = settings.feishu_default_chat_id
    if not receive_id:
        return False, None, "FEISHU_DEFAULT_CHAT_ID not configured"
    client = _getFeishuClient()
    if client is None:
        return False, receive_id, "feishu app credentials not configured"
    card = buildReminderCard(evtId=evtId, title=title, content=content)
    try:
        client.send_interactive_card(receive_id, card)
    except FeishuAPIError as exc:
        return False, receive_id, str(exc)
    return True, receive_id, None


def _deliverFeishu(
    title: str,
    content: str,
    *,
    evtId: str | None = None,
    phase: str = "end",
) -> tuple[bool, str | None, str | None]:
    if phase == "end" and evtId is not None and _sendFeishu is _baselineSendFeishu:
        return _sendFeishuReminderCard(evtId=evtId, title=title, content=content)
    return _sendFeishu(title, content)


def sendReminder(
    db: Session,
    *,
    evtId: str,
    title: str,
    content: str,
    channel: str,
    dedupKey: str | None = None,
    phase: str = "end",
) -> dict[str, str]:
    if dedupKey and crud.notifyDedupExists(db, dedupKey):
        return {"channel": channel, "stat": "deduped"}

    if channel == "screen":
        ok, fail = _sendScreen(title, content, evtId=evtId, phase=phase)
        stat = "sent" if ok else "failed"
        crud.writeNotifyLog(
            db,
            dedupKey=dedupKey if ok else None,
            channel="screen",
            title=title,
            content=content,
            stat=stat,
            evtId=evtId,
            failReason=fail,
        )
        return {"channel": "screen", "stat": stat}

    if channel == "feishu":
        ok, target_id, fail = _deliverFeishu(
            title,
            content,
            evtId=evtId,
            phase=phase,
        )
        stat = "sent" if ok else "failed"
        crud.writeNotifyLog(
            db,
            dedupKey=dedupKey if ok else None,
            channel="feishu",
            targetId=target_id,
            title=title,
            content=content,
            stat=stat,
            evtId=evtId,
            failReason=fail,
        )
        return {"channel": "feishu", "stat": stat}

    return {"channel": channel, "stat": "failed"}


def routeNotify(
    db: Session,
    *,
    title: str,
    content: str,
    screenOnline: bool,
    dedupKey: str | None = None,
    evtId: str | None = None,
    phase: str = "end",
) -> dict[str, str]:
    if dedupKey and crud.notifyDedupExists(db, dedupKey):
        return {"channel": "skipped", "stat": "deduped"}

    preference = get_user_preferences(db).get("reminderChannel", "screen")

    if preference == "feishu":
        ok, target_id, fail = _deliverFeishu(
            title,
            content,
            evtId=evtId,
            phase=phase,
        )
        stat = "sent" if ok else "failed"
        crud.writeNotifyLog(
            db,
            dedupKey=dedupKey if ok else None,
            channel="feishu",
            targetId=target_id,
            title=title,
            content=content,
            stat=stat,
            evtId=evtId,
            failReason=fail,
        )
        return {"channel": "feishu", "stat": stat}

    if not screenOnline:
        crud.writeNotifyLog(
            db,
            dedupKey=None,
            channel="screen",
            title=title,
            content=content,
            stat="failed",
            evtId=evtId,
            failReason="screen websocket offline",
        )
        return {"channel": "screen", "stat": "failed"}

    ok, fail = _sendScreen(title, content, evtId=evtId, phase=phase)
    stat = "sent" if ok else "failed"
    crud.writeNotifyLog(
        db,
        dedupKey=dedupKey if ok else None,
        channel="screen",
        title=title,
        content=content,
        stat=stat,
        evtId=evtId,
        failReason=fail,
    )
    return {"channel": "screen", "stat": stat}
