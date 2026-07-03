from __future__ import annotations

from sqlalchemy.orm import Session

from app.new_core import crud


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
        channel = "screen"
        stat = "sent"
    elif piState == "working" and not screenOnline:
        channel = "feishu"
        stat = "fallback"
    else:
        channel = "feishu"
        stat = "sent"

    crud.writeNotifyLog(
        db,
        dedupKey=dedupKey,
        channel=channel,
        title=title,
        content=content,
        stat=stat,
    )
    return {"channel": channel, "stat": stat}
