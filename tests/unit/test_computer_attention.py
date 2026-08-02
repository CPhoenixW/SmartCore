from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.server.computer.attention_service import dispatch_attention_reminders
from app.server.new_core.models import (
    AppUser,
    ComputerMonitorStatus,
    ComputerWorkBlock,
    EvtBase,
    LifeDevice,
    NotifyLog,
    PlanEvt,
)

pytestmark = pytest.mark.unit


def _fixture(db_session, *, state: str = "idle", state_since: datetime):
    user = AppUser(userId="attention-user", loginName="attention", displayName="Attention")
    device = LifeDevice(
        userId=user.userId,
        deviceName="Development Mac",
        deviceKind="computer",
        stat="active",
    )
    db_session.add_all([user, device])
    db_session.flush()
    db_session.add(
        ComputerMonitorStatus(
            deviceId=device.deviceId,
            userId=user.userId,
            currentState=state,
            stateSince=state_since.isoformat(),
            observedAt=state_since.isoformat(),
            lastHeartbeatAt=(state_since + timedelta(minutes=5)).isoformat(),
        )
    )
    db_session.commit()
    return user, device


def _enable_screen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.server.new_core.notify.screenManager.online",
        lambda _user_id=None: True,
    )
    monkeypatch.setattr(
        "app.server.new_core.notify._sendScreen",
        lambda *_args, **_kwargs: (True, None),
    )


def test_plan_idle_reminds_after_five_minutes_from_plan_start_once(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_screen(monkeypatch)
    idle_since = datetime(2026, 8, 1, 8, 50, tzinfo=UTC)
    user, device = _fixture(db_session, state_since=idle_since)
    plan_start = datetime(2026, 8, 1, 9, tzinfo=UTC)
    base = EvtBase(userId=user.userId, title="接口重构", evtType="plan", stat="todo")
    db_session.add(base)
    db_session.flush()
    db_session.add(PlanEvt(evtId=base.evtId, stTime=plan_start.isoformat(), durationMin=60))
    status = db_session.get(ComputerMonitorStatus, device.deviceId)
    status.lastHeartbeatAt = (plan_start + timedelta(minutes=5)).isoformat()
    db_session.commit()

    early = dispatch_attention_reminders(
        db_session,
        now=plan_start + timedelta(minutes=4, seconds=59),
        screen_online=lambda _user_id: True,
    )
    sent = dispatch_attention_reminders(
        db_session,
        now=plan_start + timedelta(minutes=5),
        screen_online=lambda _user_id: True,
    )
    duplicate = dispatch_attention_reminders(
        db_session,
        now=plan_start + timedelta(minutes=6),
        screen_online=lambda _user_id: True,
    )

    assert early == 0
    assert sent == 1
    assert duplicate == 0
    log = db_session.query(NotifyLog).one()
    assert log.evtId is None
    assert log.title == "计划注意力提醒"
    assert "接口重构" in log.content
    assert log.dedupKey.startswith(f"computer-attention:{device.deviceId}:")


def test_plan_idle_skips_meal_and_rest_plan(db_session) -> None:
    idle_since = datetime(2026, 8, 1, 8, 50, tzinfo=UTC)
    user, _device = _fixture(db_session, state_since=idle_since)
    plan_start = datetime(2026, 8, 1, 9, tzinfo=UTC)
    base = EvtBase(
        userId=user.userId,
        title="晚饭+休息",
        desc="6点吃晚饭，吃饭休息到7点",
        evtType="plan",
        stat="todo",
    )
    db_session.add(base)
    db_session.flush()
    db_session.add(PlanEvt(evtId=base.evtId, stTime=plan_start.isoformat(), durationMin=60))
    status = db_session.get(ComputerMonitorStatus, _device.deviceId)
    status.lastHeartbeatAt = (plan_start + timedelta(minutes=5)).isoformat()
    db_session.commit()

    assert dispatch_attention_reminders(
        db_session,
        now=plan_start + timedelta(minutes=5),
        screen_online=lambda _user_id: True,
    ) == 0
    assert db_session.query(NotifyLog).count() == 0


def test_plan_idle_uses_overlapping_computer_plan_when_life_plan_is_present(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_screen(monkeypatch)
    plan_start = datetime(2026, 8, 1, 9, tzinfo=UTC)
    user, device = _fixture(db_session, state_since=plan_start)
    for title in ("晚饭+休息", "修复后端调度"):
        base = EvtBase(userId=user.userId, title=title, evtType="plan", stat="todo")
        db_session.add(base)
        db_session.flush()
        db_session.add(PlanEvt(evtId=base.evtId, stTime=plan_start.isoformat(), durationMin=60))
    status = db_session.get(ComputerMonitorStatus, device.deviceId)
    status.lastHeartbeatAt = (plan_start + timedelta(minutes=5)).isoformat()
    db_session.commit()

    assert dispatch_attention_reminders(
        db_session,
        now=plan_start + timedelta(minutes=5),
        screen_online=lambda _user_id: True,
    ) == 1
    log = db_session.query(NotifyLog).one()
    assert "修复后端调度" in log.content


def test_implicit_focus_requires_twenty_active_minutes(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_screen(monkeypatch)
    idle_since = datetime(2026, 8, 1, 10, tzinfo=UTC)
    user, device = _fixture(db_session, state_since=idle_since)
    block = ComputerWorkBlock(
        userId=user.userId,
        deviceId=device.deviceId,
        startAt=(idle_since - timedelta(minutes=30)).isoformat(),
        timezone="UTC",
        localDate=idle_since.date().isoformat(),
        status="open",
        activeSeconds=1199,
    )
    db_session.add(block)
    db_session.commit()
    now = idle_since + timedelta(minutes=5)

    assert dispatch_attention_reminders(
        db_session, now=now, screen_online=lambda _user_id: True
    ) == 0
    block.activeSeconds = 1200
    db_session.commit()
    assert dispatch_attention_reminders(
        db_session, now=now, screen_online=lambda _user_id: True
    ) == 1
    assert db_session.query(NotifyLog).one().content == "刚才的工作已经暂停 5 分钟，要继续吗？"


@pytest.mark.parametrize("state", ["active", "locked", "sleeping", "paused", "offline"])
def test_attention_skips_non_idle_states(db_session, state: str) -> None:
    now = datetime(2026, 8, 1, 11, tzinfo=UTC)
    user, device = _fixture(db_session, state=state, state_since=now - timedelta(minutes=10))
    db_session.add(
        ComputerWorkBlock(
            userId=user.userId,
            deviceId=device.deviceId,
            startAt=(now - timedelta(hours=1)).isoformat(),
            timezone="UTC",
            localDate=now.date().isoformat(),
            status="open",
            activeSeconds=3600,
        )
    )
    db_session.commit()
    assert dispatch_attention_reminders(
        db_session, now=now, screen_online=lambda _user_id: True
    ) == 0


def test_attention_treats_a_stale_idle_heartbeat_as_offline(db_session) -> None:
    now = datetime(2026, 8, 1, 11, tzinfo=UTC)
    user, device = _fixture(db_session, state_since=now - timedelta(minutes=10))
    status = db_session.get(ComputerMonitorStatus, device.deviceId)
    status.lastHeartbeatAt = (now - timedelta(minutes=3)).isoformat()
    db_session.add(
        ComputerWorkBlock(
            userId=user.userId,
            deviceId=device.deviceId,
            startAt=(now - timedelta(hours=1)).isoformat(),
            timezone="UTC",
            localDate=now.date().isoformat(),
            status="open",
            activeSeconds=3600,
        )
    )
    db_session.commit()

    assert dispatch_attention_reminders(
        db_session, now=now, screen_online=lambda _user_id: True
    ) == 0
    assert db_session.query(NotifyLog).count() == 0


def test_new_idle_episode_can_remind_after_recovery(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_screen(monkeypatch)
    first_idle = datetime(2026, 8, 1, 12, tzinfo=UTC)
    user, device = _fixture(db_session, state_since=first_idle)
    db_session.add(
        ComputerWorkBlock(
            userId=user.userId,
            deviceId=device.deviceId,
            startAt=(first_idle - timedelta(hours=1)).isoformat(),
            timezone="UTC",
            localDate=first_idle.date().isoformat(),
            status="open",
            activeSeconds=3600,
        )
    )
    db_session.commit()
    assert dispatch_attention_reminders(
        db_session,
        now=first_idle + timedelta(minutes=5),
        screen_online=lambda _user_id: True,
    ) == 1

    second_idle = first_idle + timedelta(minutes=15)
    status = db_session.get(ComputerMonitorStatus, device.deviceId)
    status.stateSince = second_idle.isoformat()
    status.observedAt = second_idle.isoformat()
    status.lastHeartbeatAt = (second_idle + timedelta(minutes=5)).isoformat()
    db_session.commit()
    assert dispatch_attention_reminders(
        db_session,
        now=second_idle + timedelta(minutes=5),
        screen_online=lambda _user_id: True,
    ) == 1
    assert db_session.query(NotifyLog).count() == 2
