from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.server.new_core import crud
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
    """Deliver a reminder to the user's optional Screen client.

    The browser PWA is the durable notification surface. The Screen channel is
    the only realtime channel left in the core scheduler; legacy preference
    values are normalized to Screen by the preference service.
    """
    if dedupKey and crud.notifyDedupExists(db, dedupKey):
        return {"channel": "screen", "stat": "deduped"}
    if channel != "screen":
        channel = "screen"
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
    """Route deterministic reminders to the Screen when it is connected."""
    if dedupKey and crud.notifyDedupExists(db, dedupKey):
        return {"channel": "screen", "stat": "deduped"}
    if not screenOnline or not screenManager.online(userId):
        crud.writeNotifyLog(
            db,
            dedupKey=None,
            channel="screen",
            title=title,
            content=content,
            stat="failed",
            evtId=evtId,
            failReason="screen websocket offline",
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
