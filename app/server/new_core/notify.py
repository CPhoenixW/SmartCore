from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy.orm import Session

from app.server.new_core import crud
from app.server.new_core.push import send_web_push
from app.server.screen.manager import screenManager


def _assistant_message_id(
    *,
    dedupKey: str | None,
    evtId: str | None,
    title: str,
    content: str,
) -> str:
    """Build a bounded, stable id for a proactive assistant notification.

    Delivery deduplication is intentionally based on the same event identity,
    but the raw scheduler key can be longer than the assistant history limit.
    Hashing keeps the id deterministic across retries without leaking the
    notification text into the client-message-id column.
    """
    identity = dedupKey or f"{evtId or ''}:{title}:{content}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:40]
    return f"notify:{digest}"


def _mirror_to_assistant(
    db: Session,
    *,
    title: str,
    content: str,
    dedupKey: str | None,
    evtId: str | None,
    userId: str,
) -> None:
    """Append one high-signal notification to the owner's primary chat.

    The assistant is an in-app inbox for actionable reminders. It must never
    make a delivery failure fail the scheduler, so this path is best effort and
    deliberately isolated from the push/screen route.
    """
    try:
        from app.server.new_core.assistant_history import post_proactive_assistant_message

        post_proactive_assistant_message(
            db,
            user_id=userId,
            text=f"🔔 {title}\n\n{content}",
            client_message_id=_assistant_message_id(
                dedupKey=dedupKey,
                evtId=evtId,
                title=title,
                content=content,
            ),
        )
    except Exception:  # noqa: BLE001 - chat mirroring must not block delivery
        db.rollback()


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
    url: str | None = None,
    mirrorAssistant: bool = False,
) -> dict[str, str]:
    """Deliver a reminder to browser Push first, then the optional Screen client.

    Informational reminders (weather and similar) keep their existing delivery
    behavior by default. Callers can opt in to the assistant inbox for a
    high-signal reminder without changing the push/screen fallback.
    """
    def mirror() -> None:
        if mirrorAssistant:
            _mirror_to_assistant(
                db,
                title=title,
                content=content,
                dedupKey=dedupKey,
                evtId=evtId,
                userId=userId,
            )

    if dedupKey and crud.notifyDedupExists(db, dedupKey):
        mirror()
        return {"channel": "screen", "stat": "deduped"}
    browser_ok, browser_fail = send_web_push(
        db,
        user_id=userId,
        title=title,
        content=content,
        evt_id=evtId,
        url=url,
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
        mirror()
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
    mirror()
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
    url: str | None = None,
    mirrorAssistant: bool = True,
) -> dict[str, str]:
    """Route actionable reminders to browser Push, with Screen fallback.

    ``routeNotify`` is used by the scheduler and attention monitors for events
    that require a response. Those events are also mirrored into the owner's
    primary assistant conversation, which gives the PWA a durable in-app inbox
    even when a browser push or screen is unavailable. The mirror is idempotent
    and can be disabled by lower-signal callers.
    """
    def mirror() -> None:
        if mirrorAssistant:
            _mirror_to_assistant(
                db,
                title=title,
                content=content,
                dedupKey=dedupKey,
                evtId=evtId,
                userId=userId,
            )

    if dedupKey and crud.notifyDedupExists(db, dedupKey):
        mirror()
        return {"channel": "screen", "stat": "deduped"}
    browser_ok, browser_fail = send_web_push(
        db,
        user_id=userId,
        title=title,
        content=content,
        evt_id=evtId,
        url=url,
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
        mirror()
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
        mirror()
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
    mirror()
    return {"channel": "screen", "stat": stat}
