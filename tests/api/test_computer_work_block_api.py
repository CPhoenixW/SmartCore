from __future__ import annotations

import pytest

from app.server.agent.scope import issue_agent_scope
from app.server.db.session import SessionLocal
from app.server.new_core.models import (
    AppUser,
    ComputerWorkBlock,
    ComputerWorkBlockAnalysisRun,
    LifeDevice,
)

pytestmark = pytest.mark.api


def _headers(user_id: str) -> dict[str, str]:
    return {
        "X-SmartCore-Agent-Token": "agent-secret",
        "X-SmartCore-Agent-Scope": issue_agent_scope(userId=user_id, purpose="web"),
    }


def test_work_block_agent_endpoints_are_scope_owned(client) -> None:
    db = SessionLocal()
    try:
        owner = AppUser(userId="block-owner", loginName="block-owner", displayName="Owner")
        other = AppUser(userId="block-other", loginName="block-other", displayName="Other")
        device = LifeDevice(
            deviceId="block-device",
            userId=owner.userId,
            deviceName="Owner Mac",
            deviceKind="computer",
        )
        block = ComputerWorkBlock(
            blockId="block-open",
            userId=owner.userId,
            deviceId=device.deviceId,
            startAt="2026-07-29T01:00:00+00:00",
            timezone="Asia/Shanghai",
            localDate="2026-07-29",
            status="open",
        )
        run = ComputerWorkBlockAnalysisRun(
            runId="block-run",
            userId=owner.userId,
            deviceId=device.deviceId,
            blockId=block.blockId,
            triggerKey="start:block-device:test",
            triggerType="start",
            triggerData={},
            windowStart="2026-07-29T01:00:00+00:00",
            windowEnd="2026-07-29T01:05:00+00:00",
            timezone="Asia/Shanghai",
            localDate="2026-07-29",
            inputFingerprint="fingerprint",
            status="queued",
            attemptCount=1,
            lastAttemptAt="2026-07-29T01:05:00+00:00",
        )
        db.add_all([owner, other, device, block, run])
        db.commit()
    finally:
        db.close()

    foreign_read = client.get(
        "/agent/computer/work-block-context",
        params={"runId": "block-run"},
        headers=_headers("block-other"),
    )
    assert foreign_read.status_code == 404

    foreign_write = client.post(
        "/agent/computer/work-block-analysis",
        headers=_headers("block-other"),
        json={
            "runId": "block-run",
            "status": "failed",
            "promptVersion": "computer-work-block-v1",
            "errorMessage": "must not cross owners",
        },
    )
    assert foreign_write.status_code == 404

    owner_read = client.get(
        "/agent/computer/work-block-context",
        params={"runId": "block-run"},
        headers=_headers("block-owner"),
    )
    assert owner_read.status_code == 200
    assert owner_read.json()["data"]["runId"] == "block-run"
