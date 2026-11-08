from __future__ import annotations

import pytest

from app.server.new_core.assistant_history import get_primary_conversation
from app.server.new_core.models import AppUser, AssistantMessage, NotifyLog
from app.server.new_core.notify import routeNotify, sendReminder

pytestmark = pytest.mark.unit


def _user(db_session):
    user = AppUser(userId="notify-user", loginName="notify", displayName="Notify")
    db_session.add(user)
    db_session.commit()
    return user


def _screen_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.server.new_core.notify.send_web_push",
        lambda *_args, **_kwargs: (False, "browser push is not subscribed"),
    )
    monkeypatch.setattr(
        "app.server.new_core.notify.screenManager.online",
        lambda _user_id=None: True,
    )
    monkeypatch.setattr(
        "app.server.new_core.notify._sendScreen",
        lambda *_args, **_kwargs: (True, None),
    )


def test_actionable_route_is_mirrored_to_primary_assistant_once(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _user(db_session)
    _screen_fallback(monkeypatch)

    first = routeNotify(
        db_session,
        title="复习开始前 10 分钟",
        content="计划将在 10 分钟后开始",
        screenOnline=True,
        dedupKey="remindEvt:one:2026-08-01T08:50:00+08:00",
        evtId="plan-one",
        userId="notify-user",
    )
    assert first == {"channel": "screen", "stat": "sent"}

    conversation = get_primary_conversation(db_session, user_id="notify-user")
    messages = db_session.query(AssistantMessage).filter_by(conversationId=conversation.conversationId).all()
    assert len(messages) == 1
    assert messages[0].text == "🔔 复习开始前 10 分钟\n\n计划将在 10 分钟后开始"
    assert db_session.query(NotifyLog).count() == 1

    second = routeNotify(
        db_session,
        title="复习开始前 10 分钟",
        content="计划将在 10 分钟后开始",
        screenOnline=True,
        dedupKey="remindEvt:one:2026-08-01T08:50:00+08:00",
        evtId="plan-one",
        userId="notify-user",
    )
    assert second == {"channel": "screen", "stat": "deduped"}
    assert db_session.query(AssistantMessage).filter_by(conversationId=conversation.conversationId).count() == 1
    assert db_session.query(NotifyLog).count() == 1


def test_informational_send_reminder_stays_out_of_assistant_by_default(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _user(db_session)
    _screen_fallback(monkeypatch)

    result = sendReminder(
        db_session,
        evtId=None,
        title="明日天气",
        content="晴，25–31°C",
        channel="screen",
        dedupKey="weather:tomorrow:notify-user:2026-08-01",
        userId="notify-user",
    )
    assert result == {"channel": "screen", "stat": "sent"}
    assert db_session.query(AssistantMessage).count() == 0
    assert db_session.query(NotifyLog).count() == 1
