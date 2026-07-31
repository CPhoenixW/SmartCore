from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.server.main import create_app

pytestmark = pytest.mark.api


def _setup_client() -> TestClient:
    client = TestClient(create_app())
    assert (
        client.post(
            "/api/auth/setup",
            json={"password": "correct-horse-battery-staple"},
        ).status_code
        == 200
    )
    return client


def test_important_date_natural_language_falls_back_to_a_ddl(app_env, monkeypatch) -> None:
    client = _setup_client()
    monkeypatch.setattr(
        "app.server.api.ai_routes.complete_chat",
        lambda *_args, **_kwargs: "模型没有按要求输出",
    )
    response = client.post(
        "/api/llm/parse",
        json={
            "text": "依依宝宝2026年8月28号过生日，千万不能忘了给她准备礼物",
            "now": "2026-07-13T10:00:00+08:00",
        },
    )
    assert response.status_code == 200
    parsed = response.json()["data"]["parsed"]
    assert parsed["evtType"] == "ddl"
    assert parsed["title"] == "依依宝宝生日礼物"
    assert parsed["prio"] == "high"
    assert parsed["hardDdl"] is True
    assert parsed["endTime"] == "2026-08-28T09:00:00+08:00"
    assert len(parsed["plans"]) == 2


@pytest.mark.parametrize(
    ("text", "raw", "expected_type", "time_key"),
    [
        (
            "明天晚上八点复习热流体，持续30分钟",
            '{"evtType":"plan","title":"复习热流体","prio":"mid","stTime":"2026-07-14T20:00:00+08:00","durationMin":30}',
            "plan",
            "stTime",
        ),
        (
            "周五下午提醒我给导师发邮件",
            '{"evtType":"remind","title":"给导师发邮件","prio":"mid","triggerTime":"2026-07-17T15:00:00+08:00"}',
            "remind",
            "triggerTime",
        ),
        (
            "下周一之前提交机器学习作业，务必完成",
            '{"evtType":"ddl","title":"提交机器学习作业","prio":"high","endTime":"2026-07-20T09:00:00+08:00","hardDdl":true}',
            "ddl",
            "endTime",
        ),
    ],
)
def test_natural_language_event_shapes_are_loaded_into_the_form(
    app_env, monkeypatch, text, raw, expected_type, time_key
) -> None:
    client = _setup_client()
    monkeypatch.setattr("app.server.api.ai_routes.complete_chat", lambda *_args, **_kwargs: raw)
    response = client.post(
        "/api/llm/parse",
        json={"text": text, "now": "2026-07-13T10:00:00+08:00"},
    )
    assert response.status_code == 200
    parsed = response.json()["data"]["parsed"]
    assert parsed["evtType"] == expected_type
    assert parsed["title"]
    assert parsed[time_key].endswith("+08:00")


def test_agent_commute_update_is_scoped_atomic_and_does_not_duplicate_reminders(
    client, agent_headers
) -> None:
    headers = agent_headers("default")
    tools = {
        item["name"]: item
        for item in client.get("/agent/tools", headers=headers).json()["data"]["tools"]
    }
    assert tools["commutePlanUpdate"]["path"] == "/agent/db/update_commute_plan"
    plan_response = client.post(
        "/agent/db/create_event",
        headers=headers,
        json={
            "evtType": "plan",
            "title": "通勤复测工作",
            "stTime": "2026-08-01T14:00:00+08:00",
            "durationMin": 480,
        },
    )
    reminder_response = client.post(
        "/agent/db/create_event",
        headers=headers,
        json={
            "evtType": "remind",
            "title": "通勤复测出发",
            "triggerTime": "2026-08-01T08:30:00+08:00",
        },
    )
    assert plan_response.json()["ok"] is True
    assert reminder_response.json()["ok"] is True
    plan = plan_response.json()["data"]
    reminder = reminder_response.json()["data"]

    payload = {
        "planEvtId": plan["evtId"],
        "reminderEvtId": reminder["evtId"],
        "departureAt": "2026-08-01T14:00:00+08:00",
        "commuteMinutes": 90,
        "endAt": "2026-08-01T22:00:00+08:00",
    }
    updated = client.post(
        "/agent/db/update_commute_plan",
        headers=headers,
        json=payload,
    )
    repeated = client.post(
        "/agent/db/update_commute_plan",
        headers=headers,
        json=payload,
    )

    assert updated.json()["ok"] is True
    assert repeated.json()["ok"] is True
    result = repeated.json()["data"]
    assert result["plan"]["stTime"] == "2026-08-01T15:30:00+08:00"
    assert result["plan"]["durationMin"] == 390
    assert result["reminder"]["evtId"] == reminder["evtId"]
    assert result["reminder"]["triggerTime"] == "2026-08-01T14:00:00+08:00"

    reminders = client.post(
        "/agent/db/query_events",
        headers=headers,
        json={"date": "2026-08-01", "includeReminders": True},
    ).json()["data"]["items"]
    standalone = [item for item in reminders if item["evtType"] == "remind"]
    assert [item["evtId"] for item in standalone] == [reminder["evtId"]]

    denied = client.post(
        "/agent/db/update_commute_plan",
        headers=agent_headers("other-user"),
        json=payload,
    )
    assert denied.json()["ok"] is False
    assert "plan not found" in denied.json()["errors"][0]

    for path in ("/agent/db/delete_event", "/agent/evtDelete"):
        denied_delete = client.post(
            path,
            headers=agent_headers("other-user"),
            json={"evtId": plan["evtId"]},
        )
        assert denied_delete.json()["ok"] is False
        assert "evt not found" in denied_delete.json()["errors"][0]

    still_owned = client.post(
        "/agent/db/query_events",
        headers=headers,
        json={"evtId": plan["evtId"]},
    ).json()["data"]["items"]
    assert still_owned[0]["stat"] == "todo"

    naive = client.post(
        "/agent/db/update_commute_plan",
        headers=headers,
        json={**payload, "departureAt": "2026-08-01T14:00:00"},
    )
    assert naive.json()["ok"] is False
    assert "include a UTC offset" in naive.json()["errors"][0]
