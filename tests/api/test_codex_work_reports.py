from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.server.auth.security import create_session_token
from app.server.computer.service import upsert_codex_work_reports
from app.server.db.session import SessionLocal
from app.server.main import create_app
from app.server.new_core.models import AppUser, CodexWorkReport, LifeDevice
from tests.factories import pair_device

pytestmark = pytest.mark.api


def _setup_computer(client: TestClient) -> dict:
    client.post(
        "/api/auth/setup", json={"password": "correct-horse-battery-staple"}
    ).raise_for_status()
    return pair_device(client, name="Codex Mac", kind="computer")


def _report(**overrides: object) -> dict:
    payload: dict[str, object] = {
        "sourceTaskId": "task-20260730-a",
        "reportDate": "2026-07-30",
        "timezone": "Asia/Singapore",
        "projectKey": "/workspace/smartcore",
        "projectName": "SmartCore",
        "title": "Codex report ingestion",
        "summary": "Implemented and verified the owner-scoped report ingestion contract.",
        "status": "in_progress",
        "startedAt": "2026-07-30T09:00:00+08:00",
        "endedAt": "2026-07-30T10:00:00+08:00",
        "evidence": {
            "commits": ["abc123"],
            "pullRequests": [],
            "tests": ["pytest tests/api/test_codex_work_reports.py"],
        },
    }
    payload.update(overrides)
    return payload


def test_codex_report_batch_is_device_owned_and_idempotent(app_env) -> None:
    client = TestClient(create_app())
    paired = _setup_computer(client)
    headers = {"X-SmartCore-Device-Token": paired["deviceToken"]}

    first = client.post(
        "/api/computer/codex-reports/batch",
        json={"reports": [_report()]},
        headers=headers,
    )
    assert first.status_code == 200
    first_ack = first.json()["data"]["acceptedReports"][0]
    assert first_ack["created"] is True

    second = client.post(
        "/api/computer/codex-reports/batch",
        json={
            "reports": [
                _report(
                    title="Codex report completed",
                    summary="Completed the backend contract and its focused regression coverage.",
                    status="completed",
                    evidence={
                        "commits": ["abc123"],
                        "pullRequests": ["#42"],
                        "tests": ["api-tests"],
                    },
                )
            ]
        },
        headers=headers,
    )
    assert second.status_code == 200
    second_ack = second.json()["data"]["acceptedReports"][0]
    assert second_ack == {
        "reportId": first_ack["reportId"],
        "sourceTaskId": "task-20260730-a",
        "reportDate": "2026-07-30",
        "created": False,
    }

    response = client.get(
        "/api/computer/codex-reports", params={"date": "2026-07-30"}
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["count"] == 1
    assert data["items"][0] == {
        "reportId": first_ack["reportId"],
        "deviceId": paired["device"]["deviceId"],
        "sourceTaskId": "task-20260730-a",
        "reportDate": "2026-07-30",
        "timezone": "Asia/Singapore",
        "projectKey": "/workspace/smartcore",
        "projectName": "SmartCore",
        "title": "Codex report completed",
        "summary": "Completed the backend contract and its focused regression coverage.",
        "status": "completed",
        "startedAt": "2026-07-30T01:00:00+00:00",
        "endedAt": "2026-07-30T02:00:00+00:00",
        "evidence": {
            "commits": ["abc123"],
            "pullRequests": ["#42"],
            "tests": ["api-tests"],
        },
        "createdAt": data["items"][0]["createdAt"],
        "updatedAt": data["items"][0]["updatedAt"],
    }

    db = SessionLocal()
    try:
        assert db.scalar(select(func.count()).select_from(CodexWorkReport)) == 1
        stored = db.scalar(select(CodexWorkReport))
        assert stored is not None
        assert stored.userId == "default"
        assert stored.deviceId == paired["device"]["deviceId"]
    finally:
        db.close()


def test_codex_report_upsert_is_atomic_under_concurrent_retries(app_env) -> None:
    client = TestClient(create_app())
    paired = _setup_computer(client)
    barrier = Barrier(2)

    def upload(title: str) -> dict:
        db = SessionLocal()
        try:
            device = db.get(LifeDevice, paired["device"]["deviceId"])
            assert device is not None
            barrier.wait(timeout=5)
            return upsert_codex_work_reports(
                db,
                device=device,
                reports=[_report(title=title)],
            )[0]
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(upload, ["Concurrent A", "Concurrent B"]))

    assert {item["reportId"] for item in results} == {results[0]["reportId"]}
    assert sorted(item["created"] for item in results) == [False, True]
    db = SessionLocal()
    try:
        assert db.scalar(select(func.count()).select_from(CodexWorkReport)) == 1
    finally:
        db.close()


def test_codex_reports_have_a_per_user_daily_quota(app_env) -> None:
    client = TestClient(create_app())
    paired = _setup_computer(client)
    headers = {"X-SmartCore-Device-Token": paired["deviceToken"]}
    reports = [
        _report(sourceTaskId=f"task-quota-{index}", startedAt=None, endedAt=None)
        for index in range(100)
    ]

    accepted = client.post(
        "/api/computer/codex-reports/batch",
        json={"reports": reports},
        headers=headers,
    )
    assert accepted.status_code == 200
    rejected = client.post(
        "/api/computer/codex-reports/batch",
        json={"reports": [_report(sourceTaskId="task-quota-overflow")]},
        headers=headers,
    )
    assert rejected.status_code == 422

    db = SessionLocal()
    try:
        assert db.scalar(select(func.count()).select_from(CodexWorkReport)) == 100
    finally:
        db.close()


def test_codex_report_authentication_and_owner_isolation(app_env) -> None:
    client = TestClient(create_app())
    computer = _setup_computer(client)
    pi = pair_device(client, name="Desk Pi", kind="pi")
    payload = {"reports": [_report()]}

    assert client.post("/api/computer/codex-reports/batch", json=payload).status_code == 401
    assert (
        client.post(
            "/api/computer/codex-reports/batch",
            json=payload,
            headers={"X-SmartCore-Device-Token": pi["deviceToken"]},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/computer/codex-reports/batch",
            json={"userId": "other", "reports": [_report()]},
            headers={"X-SmartCore-Device-Token": computer["deviceToken"]},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/computer/codex-reports/batch",
            json={"reports": [{**_report(), "userId": "other"}]},
            headers={"X-SmartCore-Device-Token": computer["deviceToken"]},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/computer/codex-reports/batch",
            json={"reports": [{**_report(), "deviceId": "another-device"}]},
            headers={"X-SmartCore-Device-Token": computer["deviceToken"]},
        ).status_code
        == 422
    )
    client.post(
        "/api/computer/codex-reports/batch",
        json=payload,
        headers={"X-SmartCore-Device-Token": computer["deviceToken"]},
    ).raise_for_status()

    db = SessionLocal()
    try:
        db.add(
            AppUser(
                userId="other",
                loginName="other",
                displayName="Other",
                role="user",
            )
        )
        db.commit()
    finally:
        db.close()

    anonymous = TestClient(create_app())
    assert (
        anonymous.get(
            "/api/computer/codex-reports", params={"date": "2026-07-30"}
        ).status_code
        == 401
    )
    other = TestClient(create_app())
    other.cookies.set("smartcore_session", create_session_token("other"))
    response = other.get(
        "/api/computer/codex-reports",
        params={"date": "2026-07-30", "userId": "default"},
    )
    assert response.status_code == 200
    assert response.json()["data"] == {"items": [], "count": 0}

    other_computer = pair_device(other, name="Other Codex Mac", kind="computer")
    other.post(
        "/api/computer/codex-reports/batch",
        json={"reports": [_report(title="Other user's report")]},
        headers={"X-SmartCore-Device-Token": other_computer["deviceToken"]},
    ).raise_for_status()
    other_items = other.get(
        "/api/computer/codex-reports", params={"date": "2026-07-30"}
    ).json()["data"]["items"]
    default_items = client.get(
        "/api/computer/codex-reports", params={"date": "2026-07-30"}
    ).json()["data"]["items"]
    assert [item["title"] for item in other_items] == ["Other user's report"]
    assert [item["title"] for item in default_items] == ["Codex report ingestion"]

    db = SessionLocal()
    try:
        assert db.scalar(select(func.count()).select_from(CodexWorkReport)) == 2
    finally:
        db.close()


def test_codex_report_batch_validates_dates_times_text_and_bounds(app_env) -> None:
    client = TestClient(create_app())
    paired = _setup_computer(client)
    headers = {"X-SmartCore-Device-Token": paired["deviceToken"]}

    invalid_reports = [
        _report(reportDate="2026-02-30"),
        _report(reportDate=0),
        _report(timezone="Mars/Olympus"),
        _report(startedAt="2026-07-30T09:00:00"),
        _report(startedAt=0),
        _report(
            startedAt="2026-07-30T10:00:00+08:00",
            endedAt="2026-07-30T09:00:00+08:00",
        ),
        _report(summary="First paragraph.\nSecond paragraph."),
        _report(status="complete"),
        _report(title="x" * 301),
        _report(evidence={"conversation": ["must not be accepted"]}),
        _report(evidence=["must", "be", "structured"]),
        _report(evidence={"commits": ["x"] * 51}),
        _report(evidence={"tests": ["x" * 501]}),
    ]
    for report in invalid_reports:
        response = client.post(
            "/api/computer/codex-reports/batch",
            json={"reports": [report]},
            headers=headers,
        )
        assert response.status_code == 422

    duplicate = client.post(
        "/api/computer/codex-reports/batch",
        json={"reports": [_report(), _report(title="Duplicate")]},
        headers=headers,
    )
    assert duplicate.status_code == 422

    oversized = client.post(
        "/api/computer/codex-reports/batch",
        json={
            "reports": [
                _report(
                    sourceTaskId=f"task-{index}",
                    startedAt=(datetime(2026, 7, 30, tzinfo=UTC) + timedelta(minutes=index)).isoformat(),
                    endedAt=None,
                )
                for index in range(101)
            ]
        },
        headers=headers,
    )
    assert oversized.status_code == 422
    assert client.get(
        "/api/computer/codex-reports", params={"date": "2026-02-30"}
    ).status_code == 422
