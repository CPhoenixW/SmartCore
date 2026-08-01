from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.server.computer.insights import (
    fail_daily_log,
    mark_daily_log_dispatched,
    queue_daily_log,
    store_daily_log,
)
from app.server.computer.llm_analysis import ComputerAnalysisError
from app.server.computer.work_blocks import (
    build_work_block_context,
    cleanup_work_blocks,
    evaluate_work_block,
    fail_analysis_run,
    mark_run_dispatched,
    store_work_block_analysis,
)
from app.server.config import Settings
from app.server.new_core.daily_work_context import build_daily_work_context
from app.server.new_core.models import (
    AppUser,
    CodexWorkReport,
    ComputerActivityBucket,
    ComputerActivityContext,
    ComputerActivitySlice,
    ComputerWorkBlock,
    ComputerWorkBlockAnalysisRun,
    EvtBase,
    LifeDevice,
    PlanEvt,
)
from app.server.scheduler.computer_analysis import (
    dispatch_daily_work_logs,
    dispatch_work_block_analyses,
)

pytestmark = pytest.mark.unit


def _fixture_db(db_session):
    user = AppUser(userId="block-user", loginName="block-user", displayName="Block User")
    device = LifeDevice(userId=user.userId, deviceName="Development Mac", deviceKind="computer")
    db_session.add_all([user, device])
    db_session.commit()
    return user, device


def _add_activity(
    db,
    device,
    start: datetime,
    seconds: int,
    *,
    context_id: str | None = None,
    state: str = "active",
) -> None:
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
    db.add(
        ComputerActivitySlice(
            bucketId=bucket.bucketId, state=state, seconds=seconds, contextId=context_id
        )
    )
    db.commit()


def _add_context(db, device, context_id: str, *, app: str) -> None:
    db.add(
        ComputerActivityContext(
            contextId=context_id,
            userId=device.userId,
            fingerprint=context_id,
            bundleId=f"com.example.{context_id}",
            appName=app,
            windowTitle=f"{app} workspace",
            contextKind="app",
        )
    )
    db.commit()


def _add_plan(db, user_id: str, start: datetime, duration_min: int) -> str:
    base = EvtBase(userId=user_id, title="实习计划", evtType="plan")
    db.add(base)
    db.flush()
    db.add(PlanEvt(evtId=base.evtId, stTime=start.isoformat(), durationMin=duration_min))
    db.commit()
    return base.evtId


def _start_run(db, device, now: datetime):
    run, should_dispatch = evaluate_work_block(db, device=device, now=now, timezone_name="UTC")
    assert run is not None and should_dispatch
    return run


def test_active_five_minutes_queues_start_and_creates_one_block(db_session) -> None:
    _user, device = _fixture_db(db_session)
    start = datetime(2026, 7, 29, 9, tzinfo=UTC)
    _add_context(db_session, device, "ctx-a", app="Cursor")
    for offset in range(0, 5):
        _add_activity(db_session, device, start + timedelta(minutes=offset), 60, context_id="ctx-a")

    run = _start_run(db_session, device, start + timedelta(minutes=5))
    assert run.triggerType == "start"
    block = db_session.get(ComputerWorkBlock, run.blockId)
    assert block is not None and block.status == "open"
    assert db_session.query(ComputerWorkBlock).count() == 1

    stored = store_work_block_analysis(
        db_session,
        user_id=device.userId,
        payload={
            "runId": run.runId,
            "status": "complete",
            "action": "start",
            "title": "接口开发",
            "summary": "围绕服务接口推进实现并形成可继续验证的代码结果。",
            "topicKey": "api-development",
            "evidenceContextIds": ["ctx-a"],
            "planSemanticAssessments": [],
            "model": "qwen3.7-plus",
            "promptVersion": "computer-work-block-v1",
        },
    )
    assert stored["workBlock"]["status"] == "open"
    assert db_session.query(ComputerWorkBlock).count() == 1

    duplicate = store_work_block_analysis(
        db_session,
        user_id=device.userId,
        payload={
            "runId": run.runId,
            "status": "complete",
            "action": "start",
            "title": "另一个标题",
            "summary": "重复提交不应创建第二个工作块。",
            "model": "qwen3.7-plus",
            "promptVersion": "computer-work-block-v1",
        },
    )
    assert duplicate["workBlock"]["title"] == "接口开发"
    assert db_session.query(ComputerWorkBlock).count() == 1


def test_open_block_refreshes_at_twenty_active_minutes_and_then_hourly(db_session) -> None:
    _user, device = _fixture_db(db_session)
    start = datetime(2026, 8, 1, 9, tzinfo=UTC)
    _add_context(db_session, device, "ctx-a", app="Cursor")
    for offset in range(5):
        _add_activity(
            db_session,
            device,
            start + timedelta(minutes=offset),
            60,
            context_id="ctx-a",
        )
    start_run = _start_run(db_session, device, start + timedelta(minutes=5))
    started = store_work_block_analysis(
        db_session,
        user_id=device.userId,
        payload={
            "runId": start_run.runId,
            "status": "complete",
            "action": "start",
            "title": "接口开发",
            "summary": "开始实现接口并核对现有调用约束。",
            "blocker": "证据仍少",
            "topicKey": "smartcore",
            "evidenceContextIds": ["ctx-a"],
            "planSemanticAssessments": [],
            "model": "qwen3.7-plus",
            "promptVersion": "computer-work-block-v1",
        },
    )
    block_id = started["workBlock"]["blockId"]
    block = db_session.get(ComputerWorkBlock, block_id)
    assert block is not None
    assert block.evidence["summaryRevision"] == 1
    assert block.evidence["nextSummaryActiveSeconds"] == 1200

    for offset in range(5, 20):
        _add_activity(
            db_session,
            device,
            start + timedelta(minutes=offset),
            60,
            context_id="ctx-a",
        )
    refresh, should_dispatch = evaluate_work_block(
        db_session,
        device=device,
        now=start + timedelta(minutes=20),
        timezone_name="UTC",
    )
    assert refresh is not None and should_dispatch
    assert refresh.triggerType == "refresh"
    assert refresh.triggerData["activeThreshold"] == 1200
    context = build_work_block_context(db_session, device=device, run=refresh, claim=False)
    assert context["currentBlock"]["title"] == "接口开发"
    assert context["facts"]["incrementalActiveSeconds"] == 900

    refreshed = store_work_block_analysis(
        db_session,
        user_id=device.userId,
        payload={
            "runId": refresh.runId,
            "status": "complete",
            "action": "extend",
            "title": "注意力提醒",
            "summary": "已完成空闲提醒规则设计并开始补充滚动总结。",
            "progress": "确定二十分钟与每小时刷新节点。",
            "blocker": None,
            "topicKey": "smartcore",
            "evidenceContextIds": ["ctx-a"],
            "planSemanticAssessments": [],
            "model": "qwen3.7-plus",
            "promptVersion": "computer-work-block-v1",
        },
    )
    assert refreshed["workBlock"]["blockId"] == block_id
    block = db_session.get(ComputerWorkBlock, block_id)
    assert block is not None
    assert block.title == "注意力提醒"
    assert block.blocker is None
    assert block.evidence["summaryRevision"] == 2
    assert block.evidence["lastSummarizedActiveSeconds"] == 1200
    assert block.evidence["nextSummaryActiveSeconds"] == 4800

    for offset in range(20, 80):
        _add_activity(
            db_session,
            device,
            start + timedelta(minutes=offset),
            60,
            context_id="ctx-a",
        )
    hourly, hourly_dispatch = evaluate_work_block(
        db_session,
        device=device,
        now=start + timedelta(minutes=80),
        timezone_name="UTC",
    )
    assert hourly is not None and hourly_dispatch
    assert hourly.triggerType == "refresh"
    assert hourly.triggerData["activeThreshold"] == 4800
    assert db_session.query(ComputerWorkBlock).count() == 1


def test_wall_clock_idle_does_not_advance_work_block_refresh(db_session) -> None:
    _user, device = _fixture_db(db_session)
    start = datetime(2026, 8, 1, 9, tzinfo=UTC)
    block = ComputerWorkBlock(
        userId=device.userId,
        deviceId=device.deviceId,
        startAt=start.isoformat(),
        timezone="UTC",
        localDate=start.date().isoformat(),
        status="open",
        title="接口开发",
        summary="继续处理接口。",
        activeSeconds=1200,
        generatedAt=start.isoformat(),
        evidence={
            "summaryRevision": 2,
            "lastSummarizedActiveSeconds": 1200,
            "nextSummaryActiveSeconds": 4800,
        },
    )
    db_session.add(block)
    db_session.commit()
    for offset in range(20):
        _add_activity(
            db_session,
            device,
            start + timedelta(minutes=offset),
            60,
        )
    for offset in range(20, 30):
        _add_activity(
            db_session,
            device,
            start + timedelta(minutes=offset),
            60,
            state="idle",
        )

    run, should_dispatch = evaluate_work_block(
        db_session,
        device=device,
        now=start + timedelta(minutes=30),
        timezone_name="UTC",
    )
    assert run is None and not should_dispatch
    assert db_session.query(ComputerWorkBlockAnalysisRun).count() == 0


def test_refresh_waits_for_an_inflight_higher_priority_run(db_session) -> None:
    _user, device = _fixture_db(db_session)
    start = datetime(2026, 8, 1, 9, tzinfo=UTC)
    block = ComputerWorkBlock(
        userId=device.userId,
        deviceId=device.deviceId,
        startAt=start.isoformat(),
        timezone="UTC",
        localDate=start.date().isoformat(),
        status="open",
        title="接口开发",
        summary="继续处理接口。",
        generatedAt=start.isoformat(),
        evidence={"summaryRevision": 1, "nextSummaryActiveSeconds": 1200},
    )
    db_session.add(block)
    db_session.flush()
    db_session.add(
        ComputerWorkBlockAnalysisRun(
            userId=device.userId,
            deviceId=device.deviceId,
            blockId=block.blockId,
            triggerKey="plan-change-inflight",
            triggerType="plan_change",
            triggerData={},
            windowStart=start.isoformat(),
            windowEnd=(start + timedelta(minutes=20)).isoformat(),
            timezone="UTC",
            localDate=start.date().isoformat(),
            inputFingerprint="fingerprint",
            status="queued",
            attemptCount=1,
            lastAttemptAt=(start + timedelta(minutes=20)).isoformat(),
        )
    )
    db_session.commit()
    for offset in range(20):
        _add_activity(db_session, device, start + timedelta(minutes=offset), 60)

    run, should_dispatch = evaluate_work_block(
        db_session,
        device=device,
        now=start + timedelta(minutes=20),
        timezone_name="UTC",
    )
    assert run is None and not should_dispatch
    assert db_session.query(ComputerWorkBlockAnalysisRun).count() == 1


def test_latest_work_block_summary_can_reassign_project_investment(db_session) -> None:
    user, device = _fixture_db(db_session)
    db_session.add(
        CodexWorkReport(
            userId=user.userId,
            deviceId=device.deviceId,
            sourceTaskId="task-smartcore",
            reportDate="2026-08-01",
            timezone="UTC",
            projectKey="/workspace/SmartCore",
            projectName="SmartCore",
            title="完成提醒设计",
            summary="完成注意力提醒设计。",
            status="completed",
        )
    )
    block = ComputerWorkBlock(
        userId=user.userId,
        deviceId=device.deviceId,
        startAt="2026-08-01T09:00:00+00:00",
        timezone="UTC",
        localDate="2026-08-01",
        status="open",
        title="接口开发",
        summary="处理服务逻辑。",
        activeSeconds=1200,
    )
    db_session.add(block)
    db_session.commit()

    before = build_daily_work_context(
        db_session,
        user_id=user.userId,
        report_date="2026-08-01",
        timezone_name="UTC",
    )
    assert {item["projectName"]: item["activeSeconds"] for item in before["projects"]} == {
        "SmartCore": 0,
        "其他工作": 1200,
    }

    block.title = "SmartCore注意力提醒"
    block.summary = "持续更新SmartCore的Computer工作块与注意力提醒。"
    db_session.commit()
    after = build_daily_work_context(
        db_session,
        user_id=user.userId,
        report_date="2026-08-01",
        timezone_name="UTC",
    )
    assert [item["projectName"] for item in after["projects"]] == ["SmartCore"]
    assert after["projects"][0]["activeSeconds"] == 1200


def test_idle_twenty_minutes_queues_complete(db_session) -> None:
    _user, device = _fixture_db(db_session)
    start = datetime(2026, 7, 29, 9, tzinfo=UTC)
    _add_context(db_session, device, "ctx-a", app="Cursor")
    for offset in range(0, 5):
        _add_activity(db_session, device, start + timedelta(minutes=offset), 60, context_id="ctx-a")
    run = _start_run(db_session, device, start + timedelta(minutes=5))
    stored = store_work_block_analysis(
        db_session,
        user_id=device.userId,
        payload={
            "runId": run.runId,
            "status": "complete",
            "action": "start",
            "title": "接口开发",
            "summary": "围绕服务接口推进实现并形成可继续验证的代码结果。",
            "model": "qwen3.7-plus",
            "promptVersion": "computer-work-block-v1",
        },
    )
    block_id = stored["workBlock"]["blockId"]
    close_time = start + timedelta(minutes=25)
    run2, should_dispatch = evaluate_work_block(
        db_session, device=device, now=close_time, timezone_name="UTC"
    )
    assert run2 is not None and should_dispatch
    assert run2.triggerType == "complete"
    assert run2.blockId == block_id
    assert run2.triggerData["reason"] == "idle_20m"
    closed = db_session.get(ComputerWorkBlock, block_id)
    assert closed is not None and closed.status == "closed"
    assert closed.endAt == (start + timedelta(minutes=5)).isoformat()

    with pytest.raises(ValueError, match="does not match"):
        store_work_block_analysis(
            db_session,
            user_id=device.userId,
            payload={
                "runId": run2.runId,
                "status": "complete",
                "action": "ignore",
                "model": "qwen3.7-plus",
                "promptVersion": "computer-work-block-v1",
            },
        )
    failed = store_work_block_analysis(
        db_session,
        user_id=device.userId,
        payload={
            "runId": run2.runId,
            "status": "failed",
            "errorMessage": "NO_REPLY",
            "promptVersion": "computer-work-block-v1",
        },
    )
    assert failed["status"] == "failed"
    assert db_session.get(ComputerWorkBlock, block_id).status == "closed"


def test_claiming_work_block_context_holds_a_single_lease(db_session) -> None:
    _user, device = _fixture_db(db_session)
    start = datetime(2026, 7, 29, 9, tzinfo=UTC)
    for offset in range(0, 5):
        _add_activity(db_session, device, start + timedelta(minutes=offset), 60)
    run = _start_run(db_session, device, start + timedelta(minutes=5))
    mark_run_dispatched(db_session, run, now=start + timedelta(minutes=5))

    context = build_work_block_context(db_session, device=device, run=run)
    assert context["runId"] == run.runId
    with pytest.raises(ValueError, match="ready to claim|already claimed"):
        build_work_block_context(db_session, device=device, run=run)


def test_terminal_state_closes_without_restarting_from_stale_activity(db_session) -> None:
    _user, device = _fixture_db(db_session)
    start = datetime(2026, 7, 29, 9, tzinfo=UTC)
    for offset in range(0, 5):
        _add_activity(db_session, device, start + timedelta(minutes=offset), 60)
    start_run = _start_run(db_session, device, start + timedelta(minutes=5))
    _add_activity(
        db_session,
        device,
        start + timedelta(minutes=5),
        60,
        state="locked",
    )

    close_run, should_dispatch = evaluate_work_block(
        db_session,
        device=device,
        now=start + timedelta(minutes=6),
        timezone_name="UTC",
    )
    assert close_run is not None and should_dispatch
    assert close_run.triggerType == "complete"
    assert db_session.get(ComputerWorkBlock, start_run.blockId).status == "closed"

    evaluate_work_block(
        db_session,
        device=device,
        now=start + timedelta(minutes=10),
        timezone_name="UTC",
    )
    assert db_session.query(ComputerWorkBlock).count() == 1
    assert (
        db_session.query(ComputerWorkBlock).filter(ComputerWorkBlock.status == "open").count()
        == 0
    )


def test_midnight_splits_work_block_and_preserves_continuation(db_session) -> None:
    _user, device = _fixture_db(db_session)
    start = datetime(2026, 7, 29, 23, 50, tzinfo=UTC)
    block = ComputerWorkBlock(
        userId=device.userId,
        deviceId=device.deviceId,
        startAt=start.isoformat(),
        timezone="UTC",
        localDate=start.date().isoformat(),
        status="open",
    )
    db_session.add(block)
    db_session.commit()
    for offset in range(0, 20):
        _add_activity(db_session, device, start + timedelta(minutes=offset), 60)

    completion, should_dispatch = evaluate_work_block(
        db_session,
        device=device,
        now=datetime(2026, 7, 30, 0, 5, tzinfo=UTC),
        timezone_name="UTC",
    )
    assert completion is not None and should_dispatch
    assert completion.triggerData["reason"] == "midnight"
    assert db_session.get(ComputerWorkBlock, block.blockId).endAt == datetime(
        2026, 7, 30, tzinfo=UTC
    ).isoformat()

    start_run, start_dispatch = evaluate_work_block(
        db_session,
        device=device,
        now=datetime(2026, 7, 30, 0, 10, tzinfo=UTC),
        timezone_name="UTC",
    )
    assert start_run is not None and start_dispatch
    continuation = db_session.get(ComputerWorkBlock, start_run.blockId)
    assert continuation is not None
    assert continuation.startAt == datetime(2026, 7, 30, tzinfo=UTC).isoformat()
    assert continuation.continuationOfId == block.blockId


def test_plan_overlap_uses_elapsed_plan_time_not_full_duration(db_session) -> None:
    _user, device = _fixture_db(db_session)
    start = datetime(2026, 7, 29, 9, tzinfo=UTC)
    plan_id = _add_plan(db_session, device.userId, start, 9 * 60)
    _add_context(db_session, device, "ctx-a", app="Cursor")
    for offset in range(0, 30):
        _add_activity(db_session, device, start + timedelta(minutes=offset), 60, context_id="ctx-a")
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
        triggerKey="plan-elapsed",
        triggerType="start",
        triggerData={},
        windowStart=start.isoformat(),
        windowEnd=(start + timedelta(hours=1)).isoformat(),
        timezone="UTC",
        localDate=start.date().isoformat(),
        inputFingerprint="fingerprint",
        status="queued",
    )
    db_session.add(run)
    db_session.commit()
    context = build_work_block_context(db_session, device=device, run=run, claim=False)
    plan = next(item for item in context["facts"]["plans"] if item["evtId"] == plan_id)
    assert plan["elapsedSeconds"] == 3600
    assert plan["overlapRatio"] == pytest.approx(0.5, abs=0.01)

    with pytest.raises(ValueError, match="every plan"):
        store_work_block_analysis(
            db_session,
            user_id=device.userId,
            payload={
                "runId": run.runId,
                "status": "complete",
                "action": "start",
                "title": "实习开发",
                "summary": "围绕实习任务推进开发并形成了阶段性的代码结果。",
                "planSemanticAssessments": [],
                "model": "qwen3.7-plus",
                "promptVersion": "computer-work-block-v1",
            },
        )


def test_plan_end_requeues_semantic_assessment_once(db_session) -> None:
    _user, device = _fixture_db(db_session)
    start = datetime(2026, 7, 29, 9, tzinfo=UTC)
    plan_id = _add_plan(db_session, device.userId, start, 10)
    for offset in range(0, 5):
        _add_activity(db_session, device, start + timedelta(minutes=offset), 60)
    run = _start_run(db_session, device, start + timedelta(minutes=5))
    store_work_block_analysis(
        db_session,
        user_id=device.userId,
        payload={
            "runId": run.runId,
            "status": "complete",
            "action": "start",
            "title": "计划执行",
            "summary": "围绕计划事项持续推进，并保留了可继续验证的阶段结果。",
            "planSemanticAssessments": [
                {
                    "evtId": plan_id,
                    "semanticAlignment": "aligned",
                    "confidence": "high",
                    "evidenceCodes": ["matching-context"],
                }
            ],
            "model": "qwen3.7-plus",
            "promptVersion": "computer-work-block-v1",
        },
    )
    for offset in range(5, 11):
        _add_activity(db_session, device, start + timedelta(minutes=offset), 60)

    end_run, should_dispatch = evaluate_work_block(
        db_session,
        device=device,
        now=start + timedelta(minutes=11),
        timezone_name="UTC",
    )
    assert end_run is not None and should_dispatch
    assert end_run.triggerType == "plan_change"
    assert end_run.triggerData["planPhases"] == {plan_id: "ended"}
    store_work_block_analysis(
        db_session,
        user_id=device.userId,
        payload={
            "runId": end_run.runId,
            "status": "complete",
            "action": "extend",
            "planSemanticAssessments": [
                {
                    "evtId": plan_id,
                    "semanticAlignment": "aligned",
                    "confidence": "high",
                    "evidenceCodes": ["completed-window"],
                }
            ],
            "model": "qwen3.7-plus",
            "promptVersion": "computer-work-block-v1",
        },
    )
    duplicate, duplicate_dispatch = evaluate_work_block(
        db_session,
        device=device,
        now=start + timedelta(minutes=12),
        timezone_name="UTC",
    )
    assert duplicate is None and not duplicate_dispatch

    plan = db_session.get(EvtBase, plan_id)
    assert plan is not None
    plan.title = "调整后的计划"
    db_session.commit()
    changed, changed_dispatch = evaluate_work_block(
        db_session,
        device=device,
        now=start + timedelta(minutes=13),
        timezone_name="UTC",
    )
    assert changed is not None and changed_dispatch
    assert changed.triggerType == "plan_change"
    assert changed.triggerData["planIds"] == [plan_id]


def test_switch_requires_new_context_to_dominate_fifteen_minutes(db_session) -> None:
    _user, device = _fixture_db(db_session)
    start = datetime(2026, 7, 29, 9, tzinfo=UTC)
    _add_context(db_session, device, "ctx-a", app="Cursor")
    _add_context(db_session, device, "ctx-b", app="Chrome")
    block = ComputerWorkBlock(
        userId=device.userId,
        deviceId=device.deviceId,
        startAt=start.isoformat(),
        timezone="UTC",
        localDate=start.date().isoformat(),
        status="open",
        title="接口开发",
        summary="围绕服务接口推进实现并形成可继续验证的代码结果。",
        contextIds=["ctx-a"],
        evidence={"trailingContextIds": ["ctx-a"]},
    )
    db_session.add(block)
    db_session.commit()
    for offset in range(0, 15):
        _add_activity(db_session, device, start + timedelta(minutes=offset), 60, context_id="ctx-b")
    early_run, early_dispatch = evaluate_work_block(
        db_session, device=device, now=start + timedelta(minutes=5), timezone_name="UTC"
    )
    assert early_run is None and not early_dispatch
    middle_run, middle_dispatch = evaluate_work_block(
        db_session, device=device, now=start + timedelta(minutes=10), timezone_name="UTC"
    )
    assert middle_run is None and not middle_dispatch
    run, should_dispatch = evaluate_work_block(
        db_session, device=device, now=start + timedelta(minutes=15), timezone_name="UTC"
    )
    assert run is not None and should_dispatch
    assert run.triggerType == "switch"
    assert run.triggerData["candidateContextId"] == "ctx-b"
    original_candidate_start = run.triggerData["candidateStartAt"]
    mark_run_dispatched(db_session, run, now=start + timedelta(minutes=15))
    for offset in range(15, 20):
        _add_activity(db_session, device, start + timedelta(minutes=offset), 60, context_id="ctx-b")
    duplicate, duplicate_dispatch = evaluate_work_block(
        db_session,
        device=device,
        now=start + timedelta(minutes=20),
        timezone_name="UTC",
    )
    assert duplicate is not None and duplicate.runId == run.runId
    assert not duplicate_dispatch
    assert duplicate.triggerData["candidateStartAt"] == original_candidate_start

    switched = store_work_block_analysis(
        db_session,
        user_id=device.userId,
        payload={
            "runId": run.runId,
            "status": "complete",
            "action": "switch",
            "title": "资料调研",
            "summary": "转入资料检索并围绕新的问题形成可继续整理的研究上下文。",
            "topicKey": "research",
            "evidenceContextIds": ["ctx-b"],
            "planSemanticAssessments": [],
            "model": "qwen3.7-plus",
            "promptVersion": "computer-work-block-v1",
        },
    )
    assert switched["workBlock"]["status"] == "open"
    assert switched["workBlock"]["blockId"] != block.blockId
    assert db_session.get(ComputerWorkBlock, block.blockId).status == "closed"
    assert db_session.query(ComputerWorkBlock).filter(ComputerWorkBlock.status == "open").count() == 1


def test_failed_run_retries_with_stable_trigger_key(db_session) -> None:
    _user, device = _fixture_db(db_session)
    start = datetime(2026, 7, 29, 9, tzinfo=UTC)
    for offset in range(0, 5):
        _add_activity(db_session, device, start + timedelta(minutes=offset), 60)
    now = start + timedelta(minutes=5)
    run = _start_run(db_session, device, now)
    mark_run_dispatched(db_session, run, now=now)
    fail_analysis_run(db_session, row=run, error_message="NO_REPLY", now=now)
    trigger_key = run.triggerKey

    early, early_dispatch = evaluate_work_block(
        db_session,
        device=device,
        now=now + timedelta(seconds=30),
        timezone_name="UTC",
    )
    assert early is None and not early_dispatch

    retry, should_dispatch = evaluate_work_block(
        db_session,
        device=device,
        now=now + timedelta(minutes=11),
        timezone_name="UTC",
    )
    assert retry is not None and should_dispatch
    assert retry.runId == run.runId
    assert retry.triggerKey == trigger_key


def test_schema_failure_is_terminal_and_not_dispatched_again(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _user, device = _fixture_db(db_session)
    start = datetime(2026, 7, 29, 9, tzinfo=UTC)
    for offset in range(0, 10):
        _add_activity(db_session, device, start + timedelta(minutes=offset), 60)

    calls = 0

    def reject_schema(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise ComputerAnalysisError("Computer analysis validation failed: action invalid")

    monkeypatch.setattr(
        "app.server.scheduler.computer_analysis.analyze_work_block", reject_schema
    )
    settings = Settings(
        computer_analysis_timezone="UTC",
        computer_work_block_analysis_enabled=True,
    )

    first = dispatch_work_block_analyses(
        db_session,
        settings=settings,
        now=start + timedelta(minutes=5),
    )
    later = dispatch_work_block_analyses(
        db_session,
        settings=settings,
        now=start + timedelta(minutes=6),
    )

    run = db_session.query(ComputerWorkBlockAnalysisRun).one()
    assert first == {"queued": 0, "skipped": 0, "failed": 1}
    assert later == {"queued": 0, "skipped": 1, "failed": 0}
    assert calls == 1
    assert run.status == "failed"
    assert run.nextRetryAt is None
    assert "action invalid" in (run.errorMessage or "")


def test_work_block_scheduler_does_not_duplicate_an_inflight_run(db_session) -> None:
    _user, device = _fixture_db(db_session)
    start = datetime(2026, 7, 29, 9, tzinfo=UTC)
    for offset in range(0, 10):
        _add_activity(db_session, device, start + timedelta(minutes=offset), 60)
    events: list[dict] = []
    settings = Settings(
        computer_analysis_timezone="UTC",
        computer_work_block_analysis_enabled=True,
    )

    first = dispatch_work_block_analyses(
        db_session,
        settings=settings,
        now=start + timedelta(minutes=5),
        post_event=events.append,
    )
    duplicate = dispatch_work_block_analyses(
        db_session,
        settings=settings,
        now=start + timedelta(minutes=10),
        post_event=events.append,
    )

    assert first == {"queued": 1, "skipped": 0, "failed": 0}
    assert duplicate == {"queued": 0, "skipped": 1, "failed": 0}
    assert len(events) == 1


def test_work_block_cleanup_preserves_open_and_recent_records(db_session) -> None:
    _user, device = _fixture_db(db_session)
    now = datetime(2026, 7, 29, 12, tzinfo=UTC)
    old = ComputerWorkBlock(
        userId=device.userId,
        deviceId=device.deviceId,
        startAt=(now - timedelta(days=100, hours=1)).isoformat(),
        endAt=(now - timedelta(days=100)).isoformat(),
        timezone="UTC",
        localDate=(now - timedelta(days=100)).date().isoformat(),
        status="closed",
    )
    recent = ComputerWorkBlock(
        userId=device.userId,
        deviceId=device.deviceId,
        startAt=(now - timedelta(days=1, hours=1)).isoformat(),
        endAt=(now - timedelta(days=1)).isoformat(),
        timezone="UTC",
        localDate=(now - timedelta(days=1)).date().isoformat(),
        status="closed",
    )
    open_block = ComputerWorkBlock(
        userId=device.userId,
        deviceId=device.deviceId,
        startAt=(now - timedelta(days=100)).isoformat(),
        timezone="UTC",
        localDate=(now - timedelta(days=100)).date().isoformat(),
        status="open",
    )
    db_session.add_all([old, recent, open_block])
    db_session.flush()
    old_run = ComputerWorkBlockAnalysisRun(
        userId=device.userId,
        deviceId=device.deviceId,
        blockId=old.blockId,
        triggerKey="old-run",
        triggerType="complete",
        triggerData={},
        windowStart=old.startAt,
        windowEnd=old.endAt,
        timezone="UTC",
        localDate=old.localDate,
        inputFingerprint="old",
        status="complete",
        attemptCount=1,
        createdAt=(now - timedelta(days=100)).isoformat(),
        updatedAt=(now - timedelta(days=100)).isoformat(),
    )
    db_session.add(old_run)
    db_session.commit()

    assert cleanup_work_blocks(db_session, retention_days=90, now=now) == 2
    assert db_session.get(ComputerWorkBlock, old.blockId) is None
    assert db_session.get(ComputerWorkBlockAnalysisRun, old_run.runId) is None
    assert db_session.get(ComputerWorkBlock, recent.blockId) is not None
    assert db_session.get(ComputerWorkBlock, open_block.blockId) is not None


def test_daily_preview_only_requeues_when_work_block_source_changes(db_session) -> None:
    _user, device = _fixture_db(db_session)
    start = datetime(2026, 7, 29, 9, tzinfo=UTC)
    block = ComputerWorkBlock(
        userId=device.userId,
        deviceId=device.deviceId,
        startAt=start.isoformat(),
        endAt=(start + timedelta(hours=1)).isoformat(),
        timezone="UTC",
        localDate=start.date().isoformat(),
        status="closed",
        title="接口开发",
        summary="围绕服务接口推进实现并形成了可以继续验证的代码结果。",
        generatedAt=start.isoformat(),
    )
    db_session.add(block)
    db_session.commit()

    log, queued, _ = queue_daily_log(
        db_session,
        device=device,
        log_date=start.date().isoformat(),
        phase="preview",
    )
    assert log is not None and queued
    stored = store_daily_log(
        db_session,
        user_id=device.userId,
        payload={
            "deviceId": device.deviceId,
            "logDate": start.date().isoformat(),
            "status": "complete",
            "phase": "preview",
            "title": "接口推进",
            "summary": "当天围绕服务接口完成了连续开发，并形成了可以继续验证的实现结果。",
            "workBlockIds": [block.blockId],
            "model": "qwen3.7-plus",
            "promptVersion": "computer-work-block-v1",
        },
    )
    assert stored["previewRevision"] == 1

    same_log, same_queued, _ = queue_daily_log(
        db_session,
        device=device,
        log_date=start.date().isoformat(),
        phase="preview",
    )
    assert same_log is not None and not same_queued

    block.summary = "围绕服务接口完成了新的验证结果。"
    block.generatedAt = (start + timedelta(hours=2)).isoformat()
    db_session.commit()
    changed_log, changed_queued, _ = queue_daily_log(
        db_session,
        device=device,
        log_date=start.date().isoformat(),
        phase="preview",
    )
    assert changed_log is not None and changed_queued


def test_daily_log_failure_retries_and_finalization_promotes_inflight_preview(db_session) -> None:
    _user, device = _fixture_db(db_session)
    start = datetime(2026, 7, 29, 9, tzinfo=UTC)
    block = ComputerWorkBlock(
        userId=device.userId,
        deviceId=device.deviceId,
        startAt=start.isoformat(),
        timezone="UTC",
        localDate=start.date().isoformat(),
        status="open",
    )
    db_session.add(block)
    db_session.commit()

    row, queued, _ = queue_daily_log(
        db_session,
        device=device,
        log_date=start.date().isoformat(),
        phase="preview",
        now=start,
    )
    assert row is not None and queued
    mark_daily_log_dispatched(db_session, row=row, now=start)

    promoted, final_queued, _ = queue_daily_log(
        db_session,
        device=device,
        log_date=start.date().isoformat(),
        phase="final",
        now=start + timedelta(minutes=1),
    )
    assert promoted is not None and not final_queued
    assert promoted.status == "running"
    assert promoted.phase == "final"

    failed = store_daily_log(
        db_session,
        user_id=device.userId,
        payload={
            "deviceId": device.deviceId,
            "logDate": start.date().isoformat(),
            "status": "failed",
            "phase": "preview",
            "errorMessage": "NO_REPLY",
        },
    )
    assert failed["status"] == "failed"
    assert failed["phase"] == "final"
    assert failed["nextRetryAt"] is not None
    retry_at = datetime.fromisoformat(failed["nextRetryAt"])

    early, early_queued, _ = queue_daily_log(
        db_session,
        device=device,
        log_date=start.date().isoformat(),
        phase="final",
        now=retry_at - timedelta(seconds=1),
    )
    assert early is not None and not early_queued

    retry, retry_queued, _ = queue_daily_log(
        db_session,
        device=device,
        log_date=start.date().isoformat(),
        phase="final",
        now=retry_at + timedelta(seconds=1),
    )
    assert retry is not None and retry_queued
    assert retry.phase == "final"


def test_non_retryable_daily_schema_failure_stays_terminal(db_session) -> None:
    _user, device = _fixture_db(db_session)
    start = datetime(2026, 7, 29, 9, tzinfo=UTC)
    db_session.add(
        ComputerWorkBlock(
            userId=device.userId,
            deviceId=device.deviceId,
            startAt=start.isoformat(),
            timezone="UTC",
            localDate=start.date().isoformat(),
            status="open",
        )
    )
    db_session.commit()
    row, queued, _ = queue_daily_log(
        db_session,
        device=device,
        log_date=start.date().isoformat(),
        phase="final",
        now=start,
    )
    assert row is not None and queued
    mark_daily_log_dispatched(db_session, row=row, now=start)
    fail_daily_log(
        db_session,
        row=row,
        error_message="Computer analysis validation failed: title invalid",
        now=start,
        retryable=False,
    )

    terminal, terminal_queued, _ = queue_daily_log(
        db_session,
        device=device,
        log_date=start.date().isoformat(),
        phase="final",
        now=start + timedelta(days=1),
    )

    assert terminal is not None and not terminal_queued
    assert terminal.status == "failed"
    assert terminal.nextRetryAt is None


def test_daily_final_dispatch_promotes_preview_and_late_preview_cannot_downgrade_it(
    db_session,
) -> None:
    _user, device = _fixture_db(db_session)
    start = datetime(2026, 7, 29, 23, 50, tzinfo=UTC)
    db_session.add(
        ComputerWorkBlock(
            userId=device.userId,
            deviceId=device.deviceId,
            startAt=start.isoformat(),
            timezone="UTC",
            localDate=start.date().isoformat(),
            status="open",
        )
    )
    db_session.commit()
    events: list[dict] = []
    settings = Settings(computer_analysis_timezone="UTC")

    preview = dispatch_daily_work_logs(
        db_session,
        settings=settings,
        now=start,
        phase="preview",
        post_event=events.append,
    )
    assert preview == {"queued": 1, "skipped": 0, "failed": 0}
    assert events[0]["phase"] == "preview"

    final = dispatch_daily_work_logs(
        db_session,
        settings=settings,
        now=start + timedelta(minutes=9),
        phase="final",
        post_event=events.append,
    )
    assert final == {"queued": 0, "skipped": 1, "failed": 0}

    stored = store_daily_log(
        db_session,
        user_id=device.userId,
        payload={
            "deviceId": device.deviceId,
            "logDate": start.date().isoformat(),
            "status": "complete",
            "phase": "preview",
            "title": "开发推进",
            "summary": "当天围绕服务开发持续推进，并保留了可继续验证的阶段结果。",
            "model": "qwen3.7-plus",
            "promptVersion": "computer-work-block-v1",
        },
    )
    assert stored["status"] == "complete"
    assert stored["phase"] == "final"
    assert stored["finalizedAt"] is not None


def test_daily_final_recovery_retries_the_previous_date_after_a_preview_lease_expires(
    db_session,
) -> None:
    _user, device = _fixture_db(db_session)
    start = datetime(2026, 7, 29, 23, 50, tzinfo=UTC)
    db_session.add(
        ComputerWorkBlock(
            userId=device.userId,
            deviceId=device.deviceId,
            startAt=start.isoformat(),
            timezone="UTC",
            localDate=start.date().isoformat(),
            status="open",
        )
    )
    db_session.commit()
    events: list[dict] = []
    settings = Settings(computer_analysis_timezone="UTC")
    dispatch_daily_work_logs(
        db_session,
        settings=settings,
        now=start,
        phase="preview",
        post_event=events.append,
    )
    dispatch_daily_work_logs(
        db_session,
        settings=settings,
        now=start + timedelta(minutes=9),
        phase="final",
        post_event=events.append,
    )

    expired = dispatch_daily_work_logs(
        db_session,
        settings=settings,
        now=start + timedelta(minutes=16),
        phase="final",
        log_date=start.date().isoformat(),
        post_event=events.append,
    )
    assert expired == {"queued": 0, "skipped": 1, "failed": 0}

    retried = dispatch_daily_work_logs(
        db_session,
        settings=settings,
        now=start + timedelta(minutes=18),
        phase="final",
        log_date=start.date().isoformat(),
        post_event=events.append,
    )
    assert retried == {"queued": 1, "skipped": 0, "failed": 0}
    assert events[-1]["logDate"] == start.date().isoformat()
    assert events[-1]["phase"] == "final"
