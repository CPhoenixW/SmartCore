from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from app.server.computer.insights import (
    mark_daily_log_dispatched,
    queue_daily_log,
    store_daily_log,
)
from app.server.computer.llm_analysis import analyze_daily_log, analyze_work_block
from app.server.config import Settings
from app.server.new_core.models import (
    AppUser,
    ComputerActivityBucket,
    ComputerActivitySlice,
    ComputerHourlyAnalysis,
    ComputerWorkBlock,
    ComputerWorkBlockAnalysisRun,
    LifeDevice,
)
from app.server.scheduler import computer_analysis
from app.server.scheduler.computer_analysis import dispatch_hourly_analyses

pytestmark = pytest.mark.unit


def _fixture_db(db_session):
    user = AppUser(userId="direct-user", loginName="direct-user", displayName="Direct User")
    device = LifeDevice(userId=user.userId, deviceName="Development Mac", deviceKind="computer")
    db_session.add_all([user, device])
    db_session.commit()
    return user, device


def _closed_block(db_session, device, start: datetime) -> ComputerWorkBlock:
    block = ComputerWorkBlock(
        userId=device.userId,
        deviceId=device.deviceId,
        startAt=start.isoformat(),
        endAt=(start + timedelta(hours=1)).isoformat(),
        timezone="UTC",
        localDate=start.date().isoformat(),
        status="closed",
        title="接口开发",
        summary="围绕服务接口推进实现并形成了可继续验证的代码结果。",
        generatedAt=start.isoformat(),
    )
    db_session.add(block)
    db_session.commit()
    return block


def test_daily_direct_analysis_uses_flash_and_allows_one_schema_repair(db_session) -> None:
    _user, device = _fixture_db(db_session)
    start = datetime(2026, 7, 31, 9, tzinfo=UTC)
    block = _closed_block(db_session, device, start)
    row, queued, _ = queue_daily_log(
        db_session,
        device=device,
        log_date=start.date().isoformat(),
        phase="preview",
        now=start + timedelta(hours=1),
    )
    assert row is not None and queued
    mark_daily_log_dispatched(db_session, row=row, now=start + timedelta(hours=1))
    requests: list[dict] = []

    def completion(messages, **kwargs):
        requests.append({"messages": messages, **kwargs})
        if len(requests) == 1:
            return "{}"
        return json.dumps(
            {
                "title": "接口推进",
                "summary": "当天围绕服务接口持续开发，并形成了可以继续验证的实现结果。",
                "topics": [],
                "planAssessments": [],
            },
            ensure_ascii=False,
        )

    stored = analyze_daily_log(
        db_session,
        device=device,
        row=row,
        settings=Settings(
            computer_analysis_model="deepseek-v4-flash",
            computer_analysis_repair_attempts=1,
        ),
        completion=completion,
    )

    assert len(requests) == 2
    assert requests[0]["model"] == "deepseek-v4-flash"
    assert requests[0]["max_tokens"] == 2048
    assert requests[0]["response_format"] == {"type": "json_object"}
    assert requests[0]["usage_label"] == "computer_daily_work_log"
    submitted_prompt = requests[0]["messages"][1]["content"]
    assert device.userId not in submitted_prompt
    assert device.deviceId not in submitted_prompt
    assert block.blockId not in submitted_prompt
    assert stored["status"] == "complete"
    assert stored["model"] == "deepseek-v4-flash"
    assert stored["workBlockIds"] == [block.blockId]
    assert stored["previewRevision"] == 1


def test_work_block_direct_analysis_uses_server_fixed_action(db_session) -> None:
    _user, device = _fixture_db(db_session)
    start = datetime(2026, 7, 31, 9, tzinfo=UTC)
    block = ComputerWorkBlock(
        userId=device.userId,
        deviceId=device.deviceId,
        startAt=start.isoformat(),
        timezone="UTC",
        localDate=start.date().isoformat(),
        status="open",
    )
    db_session.add(block)
    db_session.flush()
    run = ComputerWorkBlockAnalysisRun(
        userId=device.userId,
        deviceId=device.deviceId,
        blockId=block.blockId,
        triggerKey="complete-direct",
        triggerType="complete",
        triggerData={"closeAt": (start + timedelta(hours=1)).isoformat()},
        windowStart=start.isoformat(),
        windowEnd=(start + timedelta(hours=1)).isoformat(),
        timezone="UTC",
        localDate=start.date().isoformat(),
        inputFingerprint="fingerprint",
        status="queued",
        attemptCount=1,
    )
    db_session.add(run)
    db_session.commit()

    stored = analyze_work_block(
        db_session,
        device=device,
        run=run,
        settings=Settings(computer_analysis_model="deepseek-v4-flash"),
        completion=lambda _messages, **_kwargs: json.dumps(
            {
                "action": "ignore",
                "planSemanticAssessments": [],
                "evidenceContextIds": [],
            }
        ),
    )

    assert stored["run"]["action"] == "complete"
    assert stored["workBlock"]["status"] == "closed"
    assert stored["workBlock"]["model"] == "deepseek-v4-flash"


def test_daily_preview_throttles_changed_source_until_interval_expires(db_session) -> None:
    _user, device = _fixture_db(db_session)
    start = datetime(2026, 7, 31, 9, tzinfo=UTC)
    block = _closed_block(db_session, device, start)
    row, queued, _ = queue_daily_log(
        db_session,
        device=device,
        log_date=start.date().isoformat(),
        phase="preview",
        now=start,
    )
    assert row is not None and queued
    store_daily_log(
        db_session,
        user_id=device.userId,
        payload={
            "deviceId": device.deviceId,
            "logDate": start.date().isoformat(),
            "status": "complete",
            "phase": "preview",
            "title": "接口推进",
            "summary": "当天围绕服务接口持续开发，并形成了可以继续验证的实现结果。",
            "model": "deepseek-v4-flash",
            "promptVersion": "computer-work-block-v1",
        },
    )
    row.generatedAt = start.isoformat()
    block.summary = "围绕服务接口完成了新的验证结果。"
    block.generatedAt = (start + timedelta(minutes=10)).isoformat()
    db_session.commit()

    throttled, throttled_queued, _ = queue_daily_log(
        db_session,
        device=device,
        log_date=start.date().isoformat(),
        phase="preview",
        now=start + timedelta(minutes=30),
        preview_min_interval_minutes=60,
    )
    assert throttled is not None and not throttled_queued

    released, released_queued, _ = queue_daily_log(
        db_session,
        device=device,
        log_date=start.date().isoformat(),
        phase="preview",
        now=start + timedelta(minutes=61),
        preview_min_interval_minutes=60,
    )
    assert released is not None and released_queued


def test_direct_analysis_failure_falls_back_to_openclaw(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[dict] = []
    monkeypatch.setattr(computer_analysis, "_post", lambda _settings, event: events.append(event))
    event = {"event_type": "computer_daily_work_log", "event_id": "daily-1"}

    computer_analysis._analyze_or_deliver(
        db_session,
        settings=Settings(
            computer_analysis_direct_llm_enabled=True,
            computer_analysis_openclaw_fallback_enabled=True,
        ),
        post_event=None,
        event=event,
        analyze=lambda: (_ for _ in ()).throw(RuntimeError("flash unavailable")),
    )

    assert events == [event]


def test_work_block_mode_keeps_hourly_snapshot_objective_without_ai(db_session) -> None:
    _user, device = _fixture_db(db_session)
    hour = datetime(2026, 7, 31, 9, tzinfo=UTC)
    bucket = ComputerActivityBucket(
        userId=device.userId,
        deviceId=device.deviceId,
        sessionId="session-1",
        bucketStart=hour.isoformat(),
        timezone="UTC",
        localDate=hour.date().isoformat(),
        coveredSeconds=60,
        switchCount=0,
    )
    db_session.add(bucket)
    db_session.flush()
    db_session.add(ComputerActivitySlice(bucketId=bucket.bucketId, state="active", seconds=60))
    db_session.commit()
    events: list[dict] = []

    result = dispatch_hourly_analyses(
        db_session,
        settings=Settings(
            computer_analysis_timezone="UTC",
            computer_work_block_analysis_enabled=True,
        ),
        now=hour + timedelta(hours=1, minutes=5),
        post_event=events.append,
    )

    row = db_session.query(ComputerHourlyAnalysis).one()
    assert result == {"queued": 1, "skipped": 0, "failed": 0}
    assert events == []
    assert row.status == "complete"
    assert row.promptVersion == "objective-v1"
    assert row.model is None
