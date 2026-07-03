from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import get_settings
from app.feishu.client import FeishuAPIError, FeishuClient
from app.new_core import crud
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


def _sendScreen(title: str, content: str) -> tuple[bool, str | None]:
    ok = screenManager.broadcastFromThread(
        {"kind": "reminder", "title": title, "content": content}
    )
    return ok, None if ok else "screen websocket offline"


def _sendFeishu(title: str, content: str) -> tuple[bool, str | None, str | None]:
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


def routeNotify(
    db: Session,
    *,
    title: str,
    content: str,
    screenOnline: bool,
    dedupKey: str | None = None,
) -> dict[str, str]:
    if dedupKey and crud.notifyDedupExists(db, dedupKey):
        return {"channel": "skipped", "stat": "deduped"}

    latest = crud.getLatestDevState(db, devId="pi")
    piState = latest["state"] if latest else "unknown"

    if piState == "working" and screenOnline:
        ok, fail = _sendScreen(title, content)
        if ok:
            crud.writeNotifyLog(
                db,
                dedupKey=dedupKey,
                channel="screen",
                title=title,
                content=content,
                stat="sent",
            )
            return {"channel": "screen", "stat": "sent"}
        fallback_ok, target_id, fallback_fail = _sendFeishu(title, content)
        stat = "fallback" if fallback_ok else "failed"
        crud.writeNotifyLog(
            db,
            dedupKey=dedupKey if fallback_ok else None,
            channel="feishu",
            targetId=target_id,
            title=title,
            content=content,
            stat=stat,
            failReason=None if fallback_ok else f"{fail}; {fallback_fail}",
        )
        return {"channel": "feishu", "stat": stat}

    ok, target_id, fail = _sendFeishu(title, content)
    if piState == "working" and not screenOnline and ok:
        stat = "fallback"
    else:
        stat = "sent" if ok else "failed"
    crud.writeNotifyLog(
        db,
        dedupKey=dedupKey if ok else None,
        channel="feishu",
        targetId=target_id,
        title=title,
        content=content,
        stat=stat,
        failReason=fail,
    )
    return {"channel": "feishu", "stat": stat}
