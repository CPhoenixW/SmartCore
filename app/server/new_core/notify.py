from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.server.new_core import crud
from app.server.new_core.push import send_web_push
from app.server.screen.manager import screenManager


def _sendScreen(
    title: str,
    content: str,
    *,
    evtId: str | None = None,
    phase: str = "end",
    userId: str = crud.DEFAULT_USER_ID,
) -> tuple[bool, str | None]:
    if phase == "start":
        message: dict[str, Any] = {
            "kind": "reminderSound",
            "title": title,
            "content": content,
        }
    else:
        message = {"kind": "reminder", "title": title, "content": content}
        if evtId:
            message["evtId"] = evtId
    ok = screenManager.broadcastFromThread(message, userId=userId)
    return ok, None if ok else "screen websocket offline"


def sendReminder(
    db: Session,
    *,
    evtId: str | None,
    title: str,
    content: str,
    channel: str,
    dedupKey: str | None = None,
    phase: str = "end",
    userId: str = crud.DEFAULT_USER_ID,
) -> dict[str, str]:
    """Deliver a reminder to browser Push first, then the optional Screen client."""
    if dedupKey and crud.notifyDedupExists(db, dedupKey):
        return {"channel": "screen", "stat": "deduped"}
    browser_ok, browser_fail = send_web_push(
        db,
        user_id=userId,
        title=title,
        content=content,
        evt_id=evtId,
    )
    if browser_ok:
        crud.writeNotifyLog(
            db,
            dedupKey=dedupKey,
            channel="browser",
            title=title,
            content=content,
            stat="sent",
            evtId=evtId,
            userId=userId,
        )
        return {"channel": "browser", "stat": "sent"}
    ok, fail = _sendScreen(title, content, evtId=evtId, phase=phase, userId=userId)
    stat = "sent" if ok else "failed"
    crud.writeNotifyLog(
        db,
        dedupKey=dedupKey if ok else None,
        channel="screen",
        title=title,
        content=content,
        stat=stat,
        evtId=evtId,
        failReason=fail or browser_fail,
        userId=userId,
    )
    return {"channel": "screen", "stat": stat}


def routeNotify(
    db: Session,
    *,
    title: str,
    content: str,
    screenOnline: bool,
    dedupKey: str | None = None,
    evtId: str | None = None,
    phase: str = "end",
    userId: str = crud.DEFAULT_USER_ID,
) -> dict[str, str]:
    """Route deterministic reminders to browser Push, with Screen fallback."""
    if dedupKey and crud.notifyDedupExists(db, dedupKey):
        return {"channel": "screen", "stat": "deduped"}
    browser_ok, browser_fail = send_web_push(
        db,
        user_id=userId,
        title=title,
        content=content,
        evt_id=evtId,
    )
    if browser_ok:
        crud.writeNotifyLog(
            db,
            dedupKey=dedupKey,
            channel="browser",
            title=title,
            content=content,
            stat="sent",
            evtId=evtId,
            userId=userId,
        )
        return {"channel": "browser", "stat": "sent"}
    if not screenOnline or not screenManager.online(userId):
        crud.writeNotifyLog(
            db,
            dedupKey=None,
            channel="screen",
            title=title,
            content=content,
            stat="failed",
            evtId=evtId,
            failReason=f"{browser_fail}; screen websocket offline" if browser_fail else "screen websocket offline",
            userId=userId,
        )
        return {"channel": "screen", "stat": "failed"}
    ok, fail = _sendScreen(title, content, evtId=evtId, phase=phase, userId=userId)
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
        userId=userId,
    )
    return {"channel": "screen", "stat": stat}
