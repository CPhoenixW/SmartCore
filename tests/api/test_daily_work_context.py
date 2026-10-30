from __future__ import annotations

import pytest

from app.server.db.session import SessionLocal
from app.server.new_core.event_relations import create_plan_event
from app.server.new_core.models import (
    CodexWorkReport,
    ComputerActivityContext,
    ComputerWorkBlock,
    EvtBase,
    LifeDevice,
)
from tests.factories import create_user

pytestmark = pytest.mark.api


def test_daily_work_context_is_owner_scoped_and_groups_project_investment(
    client, agent_headers, signed_client_factory
) -> None:
    db = SessionLocal()
    try:
        create_user(db, user_id="context-owner")
        create_user(db, user_id="context-other")
        device = LifeDevice(
            deviceId="context-mac",
            userId="context-owner",
            deviceName="Owner Mac",
            deviceKind="computer",
        )
        matched_context = ComputerActivityContext(
            contextId="context-smartcore",
            userId="context-owner",
            fingerprint="fingerprint-smartcore",
            bundleId="com.todesktop.cursor",
            appName="Cursor",
            workspace="SmartCore",
        )
        unmatched_context = ComputerActivityContext(
            contextId="context-other-work",
            userId="context-owner",
            fingerprint="fingerprint-other",
            bundleId="com.apple.Safari",
            appName="Safari",
            windowTitle="阅读资料",
        )
        db.add_all(
            [
                device,
                matched_context,
                unmatched_context,
                CodexWorkReport(
                    userId="context-owner",
                    deviceId=device.deviceId,
                    sourceTaskId="task-smartcore",
                    reportDate="2026-07-30",
                    timezone="Asia/Shanghai",
                    projectKey="/Users/phoenixw/SmartCore",
                    projectName="SmartCore",
                    title="完成日报链路",
                    summary="完成项目日报数据链并通过接口测试。",
                    status="completed",
                ),
                ComputerWorkBlock(
                    blockId="block-smartcore",
                    userId="context-owner",
                    deviceId=device.deviceId,
                    startAt="2026-07-30T09:00:00+08:00",
                    endAt="2026-07-30T09:30:00+08:00",
                    timezone="Asia/Shanghai",
                    localDate="2026-07-30",
                    status="closed",
                    title="日报开发",
                    activeSeconds=1800,
                    plannedActiveSeconds=1200,
                    contextIds=[matched_context.contextId],
                ),
                ComputerWorkBlock(
                    blockId="block-unmatched",
                    userId="context-owner",
                    deviceId=device.deviceId,
                    startAt="2026-07-30T10:00:00+08:00",
                    endAt="2026-07-30T10:10:00+08:00",
                    timezone="Asia/Shanghai",
                    localDate="2026-07-30",
                    status="closed",
                    title="Users research",
                    activeSeconds=600,
                    contextIds=[unmatched_context.contextId],
                ),
            ]
        )
        db.commit()
        plan = create_plan_event(
            db,
            title="SmartCore 发布",
            desc="执行结果：候选环境验证通过",
            stTime="2026-07-30T22:00:00+08:00",
            durationMin=30,
            userId="context-owner",
        )
        db.get(EvtBase, plan["evtId"]).stat = "done"
        db.commit()
    finally:
        db.close()

    response = client.get(
        "/agent/daily-work-context",
        params={"date": "2026-07-30", "timezone": "Asia/Shanghai"},
        headers=agent_headers("context-owner"),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["evidencePriority"] == [
        "human_completion",
        "codex_report",
        "work_block",
    ]
    assert data["totals"]["activeSeconds"] == 2400
    projects = {item["projectName"]: item for item in data["projects"]}
    assert projects["SmartCore"]["activeSeconds"] == 1800
    assert projects["SmartCore"]["statusCounts"]["completed"] == 1
    assert projects["SmartCore"]["plans"][0]["description"] == "执行结果：候选环境验证通过"
    assert projects["其他工作"]["activeSeconds"] == 600

    foreign = client.get(
        "/agent/daily-work-context",
        params={"date": "2026-07-30"},
        headers=agent_headers("context-other"),
    )
    assert foreign.status_code == 200
    assert foreign.json()["data"]["projects"] == []
    assert foreign.json()["data"]["codexReports"] == []

    browser = signed_client_factory("context-owner")
    insights = browser.get(
        "/api/computer/insights",
        params={"deviceId": "context-mac", "date": "2026-07-30"},
    )
    assert insights.status_code == 200
    assert insights.json()["data"]["projects"][0]["projectName"] == "SmartCore"


def test_computer_insights_limits_project_investment_to_selected_device(
    client, agent_headers, signed_client_factory
) -> None:
    db = SessionLocal()
    try:
        create_user(db, user_id="multi-computer-owner")
        first = LifeDevice(
            deviceId="multi-mac-a",
            userId="multi-computer-owner",
            deviceName="Mac A",
            deviceKind="computer",
        )
        second = LifeDevice(
            deviceId="multi-mac-b",
            userId="multi-computer-owner",
            deviceName="Mac B",
            deviceKind="computer",
        )
        db.add_all(
            [
                first,
                second,
                CodexWorkReport(
                    userId="multi-computer-owner",
                    deviceId=first.deviceId,
                    sourceTaskId="task-alpha",
                    reportDate="2026-07-30",
                    timezone="Asia/Shanghai",
                    projectKey="project-alpha",
                    projectName="Alpha",
                    title="Alpha delivery",
                    summary="Completed Alpha work.",
                    status="completed",
                ),
                CodexWorkReport(
                    userId="multi-computer-owner",
                    deviceId=second.deviceId,
                    sourceTaskId="task-beta",
                    reportDate="2026-07-30",
                    timezone="Asia/Shanghai",
                    projectKey="project-beta",
                    projectName="Beta",
                    title="Beta delivery",
                    summary="Completed Beta work.",
                    status="completed",
                ),
                ComputerWorkBlock(
                    blockId="block-alpha",
                    userId="multi-computer-owner",
                    deviceId=first.deviceId,
                    startAt="2026-07-30T09:00:00+08:00",
                    endAt="2026-07-30T09:05:00+08:00",
                    timezone="Asia/Shanghai",
                    localDate="2026-07-30",
                    status="closed",
                    title="Alpha work",
                    activeSeconds=300,
                ),
                ComputerWorkBlock(
                    blockId="block-beta",
                    userId="multi-computer-owner",
                    deviceId=second.deviceId,
                    startAt="2026-07-30T10:00:00+08:00",
                    endAt="2026-07-30T10:10:00+08:00",
                    timezone="Asia/Shanghai",
                    localDate="2026-07-30",
                    status="closed",
                    title="Beta work",
                    activeSeconds=600,
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    daily = client.get(
        "/agent/daily-work-context",
        params={"date": "2026-07-30"},
        headers=agent_headers("multi-computer-owner"),
    )
    assert daily.status_code == 200
    assert daily.json()["data"]["totals"]["activeSeconds"] == 900

    browser = signed_client_factory("multi-computer-owner")
    response = browser.get(
        "/api/computer/insights",
        params={"deviceId": "multi-mac-a", "date": "2026-07-30"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["projectTotals"]["activeSeconds"] == 300
    assert [item["projectName"] for item in data["projects"]] == ["Alpha"]


def test_daily_summary_scope_only_exposes_daily_context_and_persistence(
    client, agent_headers
) -> None:
    headers = agent_headers(
        "default", purpose="daily_summary", report_date="2026-07-30"
    )

    tools = client.get("/agent/tools", headers=headers)
    assert tools.status_code == 200
    assert [item["name"] for item in tools.json()["data"]["tools"]] == [
        "dailyWorkContext"
    ]
    context = client.get(
        "/agent/daily-work-context",
        params={"date": "2026-07-30"},
        headers=headers,
    )
    assert context.status_code == 200
    saved = client.post(
        "/agent/daily-summary",
        json={"reportDate": "2026-07-30", "stat": "failed"},
        headers=headers,
    )
    assert saved.status_code == 200
    assert (
        client.get(
            "/agent/daily-work-context",
            params={"date": "2026-07-29"},
            headers=headers,
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/agent/daily-summary",
            json={"reportDate": "2026-07-29", "stat": "failed"},
            headers=headers,
        ).status_code
        == 403
    )

    assert (
        client.post("/agent/db/create_event", json={}, headers=headers).status_code
        == 403
    )
    assert (
        client.post("/agent/db/delete_event", json={}, headers=headers).status_code
        == 403
    )
    assert (
        client.post(
            "/agent/db/delete_event",
            json={},
            headers={"X-SmartCore-Agent-Token": "agent-secret"},
        ).status_code
        == 401
    )
    assert (
        client.post("/agent/feedback/send_text", json={"text": "removed"}, headers=headers).status_code
        == 404
    )
