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
