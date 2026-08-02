from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.server.computer.insights import (
    build_hour_context,
    dispatch_smart_plan_reminders,
    queue_hourly_analysis,
    store_hourly_analysis,
)
from app.server.computer.plan_activity import plan_computer_activity_expected
from app.server.new_core.models import (
    AppUser,
    ComputerActivityBucket,
    ComputerActivitySlice,
    ComputerHourlyAnalysis,
    EvtBase,
    LifeDevice,
    PlanEvt,
)

pytestmark = pytest.mark.unit


def _fixture_db(db_session):
    user = AppUser(userId="insight-user", loginName="insight-user", displayName="Insight User")
    device = LifeDevice(userId=user.userId, deviceName="Development Mac", deviceKind="computer")
    db_session.add_all([user, device])
    db_session.commit()
    return user, device


def _add_activity(db, device, start: datetime, seconds: int) -> None:
    bucket = ComputerActivityBucket(
        userId=device.userId,
        deviceId=device.deviceId,
        sessionId="session-1",
        bucketStart=start.isoformat(),
        timezone="UTC",
        localDate=start.date().isoformat(),
        coveredSeconds=seconds,
        switchCount=0,
    )
    db.add(bucket)
    db.flush()
    db.add(ComputerActivitySlice(bucketId=bucket.bucketId, state="active", seconds=seconds))
    db.commit()


def _add_plan(
    db,
    user_id: str,
    start: datetime,
    duration_min: int,
    *,
    title: str = "Focus task",
    desc: str | None = None,
) -> str:
    base = EvtBase(userId=user_id, title=title, desc=desc, evtType="plan")
    db.add(base)
    db.flush()
    db.add(PlanEvt(evtId=base.evtId, stTime=start.isoformat(), durationMin=duration_min))
    db.commit()
    return base.evtId


@pytest.mark.parametrize(
    ("title", "description", "expected"),
    [
        ("晚饭+休息", "6点吃晚饭，吃饭休息到7点", False),
        ("午睡", None, False),
        ("Gym workout", None, False),
        ("晚饭后写代码", None, True),
        ("REST API 调试", None, True),
        ("看VLA论文", None, True),
        ("阅读", "不需要电脑", False),
    ],
)
def test_plan_computer_activity_expectation(
    title: str, description: str | None, expected: bool
) -> None:
    assert plan_computer_activity_expected(title, description) is expected


def test_low_overlap_reminder_skips_non_computer_plan(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _user, device = _fixture_db(db_session)
    start = datetime(2026, 8, 2, 10, tzinfo=UTC)
    _add_plan(
        db_session,
        device.userId,
        start,
        60,
        title="晚饭+休息",
        desc="吃晚饭，休息到下一项计划开始",
    )
    captured: list[dict] = []
    monkeypatch.setattr(
        "app.server.computer.insights.routeNotify",
        lambda *args, **kwargs: captured.append(kwargs) or {"stat": "sent"},
    )

    assert dispatch_smart_plan_reminders(
        db_session,
        now=start + timedelta(minutes=60),
        screen_online=lambda _user_id: True,
    ) == 0
    assert captured == []


def test_low_overlap_reminder_keeps_computer_plan(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _user, device = _fixture_db(db_session)
    start = datetime(2026, 8, 2, 10, tzinfo=UTC)
    event_id = _add_plan(
        db_session,
        device.userId,
        start,
        60,
        title="修复 API 调度 bug",
    )
    captured: list[dict] = []
    monkeypatch.setattr(
        "app.server.computer.insights.routeNotify",
        lambda *args, **kwargs: captured.append(kwargs) or {"stat": "sent"},
    )

    assert dispatch_smart_plan_reminders(
        db_session,
        now=start + timedelta(minutes=60),
        screen_online=lambda _user_id: True,
    ) == 1
    assert len(captured) == 1
    assert captured[0]["evtId"] == event_id


def test_low_overlap_reminder_skips_completed_computer_plan(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _user, device = _fixture_db(db_session)
    start = datetime(2026, 8, 2, 10, tzinfo=UTC)
    event_id = _add_plan(
        db_session,
        device.userId,
        start,
        60,
        title="修复 API 调度 bug",
    )
    db_session.get(EvtBase, event_id).stat = "done"
    db_session.commit()
    captured: list[dict] = []
    monkeypatch.setattr(
        "app.server.computer.insights.routeNotify",
        lambda *args, **kwargs: captured.append(kwargs) or {"stat": "sent"},
    )

    assert dispatch_smart_plan_reminders(
        db_session,
        now=start + timedelta(minutes=60),
        screen_online=lambda _user_id: True,
    ) == 0
    assert captured == []


def test_hour_context_counts_overlapping_plans_as_one_union(db_session) -> None:
    _user, device = _fixture_db(db_session)
    hour = datetime(2026, 7, 27, 9, tzinfo=UTC)
    _add_plan(db_session, device.userId, hour, 20)
    _add_plan(db_session, device.userId, hour + timedelta(minutes=10), 20)
    _add_activity(db_session, device, hour + timedelta(minutes=10), 60)

    context = build_hour_context(
        db_session, device=device, hour_start=hour, timezone_name="UTC"
    )

    assert context["plannedActiveSeconds"] == 60
    assert sum(plan["activeSeconds"] for plan in context["plans"]) == 120


def test_hourly_result_rejects_substantial_without_seventy_percent_overlap(db_session) -> None:
    _user, device = _fixture_db(db_session)
    hour = datetime(2026, 7, 27, 9, tzinfo=UTC)
    plan_id = _add_plan(db_session, device.userId, hour, 10)
    _add_activity(db_session, device, hour + timedelta(minutes=5), 30)
    row, queued, _ = queue_hourly_analysis(
        db_session, device=device, hour_start=hour, timezone_name="UTC"
    )
    assert row is not None and queued

    with pytest.raises(ValueError, match="70%"):
        store_hourly_analysis(
            db_session,
            user_id=device.userId,
            payload={
                "deviceId": device.deviceId,
                "hourStart": row.hourStart,
                "status": "complete",
                "title": "低重叠",
                "summary": "实际活跃时间不足以支持高执行判断。",
                "planAssessments": [
                    {
                        "evtId": plan_id,
                        "state": "substantially_executed",
                        "confidence": "high",
                        "evidenceCodes": ["overlap"],
                    }
                ],
                "topics": [],
                "model": "qwen3.7-plus",
                "promptVersion": "computer-analysis-v1",
            },
        )
    db_session.rollback()
    assert db_session.get(ComputerHourlyAnalysis, row.analysisId).status == "queued"


def test_hourly_result_accepts_equivalent_zulu_hour_start(db_session) -> None:
    _user, device = _fixture_db(db_session)
    hour = datetime(2026, 7, 27, 9, tzinfo=UTC)
    _add_activity(db_session, device, hour, 60)
    row, queued, _ = queue_hourly_analysis(
        db_session, device=device, hour_start=hour, timezone_name="UTC"
    )
    assert row is not None and queued
    assert row.hourStart == "2026-07-27T09:00:00+00:00"

    result = store_hourly_analysis(
        db_session,
        user_id=device.userId,
        payload={
            "deviceId": device.deviceId,
            "hourStart": "2026-07-27T09:00:00Z",
            "status": "complete",
            "title": "开发工作",
            "summary": "本小时主要进行了开发工作。",
            "planAssessments": [],
            "topics": [],
            "model": "qwen3.7-plus",
            "promptVersion": "computer-analysis-v1",
        },
    )

    assert result["status"] == "complete"
    assert result["title"] == "开发工作"


def test_zero_active_cannot_be_marked_partial(db_session) -> None:
    _user, device = _fixture_db(db_session)
    hour = datetime(2026, 7, 27, 9, tzinfo=UTC)
    plan_id = _add_plan(db_session, device.userId, hour, 10)
    row, queued, _ = queue_hourly_analysis(
        db_session, device=device, hour_start=hour, timezone_name="UTC"
    )
    assert row is not None and queued and row.activeSeconds == 0

    with pytest.raises(ValueError, match="activeSeconds is zero"):
        store_hourly_analysis(
            db_session,
            user_id=device.userId,
            payload={
                "deviceId": device.deviceId,
                "hourStart": row.hourStart,
                "status": "complete",
                "title": "无活跃",
                "summary": "没有采集到电脑活跃事实。",
                "planAssessments": [
                    {
                        "evtId": plan_id,
                        "state": "partial",
                        "confidence": "low",
                        "evidenceCodes": [],
                    }
                ],
                "topics": [],
                "model": "qwen3.7-plus",
                "promptVersion": "computer-analysis-v1",
            },
        )
