from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import httpx
import pytest
from sqlalchemy import select

from app.server.agent.scope import issue_agent_scope
from app.server.config import Settings
from app.server.db.session import SessionLocal
from app.server.main import create_app
from app.server.new_core.daily_summary_service import store_daily_summary
from app.server.new_core.event_relations import create_plan_event
from app.server.new_core.models import (
    AppUser,
    DailySummary,
    FeishuBind,
    FeishuBot,
    LifeIdentity,
)
from app.server.scheduler.daily_summary import dispatch_daily_summaries
from app.server.scheduler.service import SchedulerService
from app.server.weather.service import deliver_tomorrow_weather, get_weather, refresh_weather
from openclaw.adapter import adapter

pytestmark = pytest.mark.api


def _agent_headers(user_id: str) -> dict[str, str]:
    return {
        "X-SmartCore-Agent-Token": "agent-secret",
        "X-SmartCore-Agent-Scope": issue_agent_scope(
            userId=user_id,
            botId="bot-test",
            chatId=f"chat-{user_id}",
        ),
    }


def test_completion_summary_appends_description_and_is_owner_scoped(
    app_env,
    signed_client_factory,
) -> None:
    db = SessionLocal()
    try:
        db.add_all(
            [
                AppUser(userId="owner", loginName="owner", displayName="Owner"),
                AppUser(userId="other", loginName="other", displayName="Other"),
            ]
        )
        db.commit()
        event = create_plan_event(
            db,
            userId="owner",
            title="Finish report",
            stTime="2026-07-19T18:00:00+08:00",
            durationMin=60,
            desc="Original context",
        )
    finally:
        db.close()

    owner = signed_client_factory("owner")
    completed = owner.post(
        "/agent/db/complete_event",
        headers=_agent_headers("owner"),
        json={"evtId": event["evtId"], "summary": "Finished the analysis and learned X."},
    )
    assert completed.status_code == 200
    assert completed.json()["data"]["stat"] == "done"
    description = completed.json()["data"]["desc"]
    assert description == "Original context\n\n完成总结：Finished the analysis and learned X."

    repeated = owner.post(
        "/agent/db/complete_event",
        headers=_agent_headers("owner"),
        json={"evtId": event["evtId"], "summary": "Finished the analysis and learned X."},
    )
    assert repeated.json()["data"]["desc"].count("完成总结：") == 1

    rejected = owner.post(
        "/agent/db/complete_event",
        headers=_agent_headers("other"),
        json={"evtId": event["evtId"], "summary": "Steal it"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["ok"] is False
    assert "not found" in rejected.json()["errors"][0]


def test_daily_summary_write_and_browser_read_are_user_scoped(
    app_env,
    signed_client_factory,
) -> None:
    db = SessionLocal()
    try:
        db.add_all(
            [
                AppUser(userId="owner", loginName="owner", displayName="Owner"),
                AppUser(userId="other", loginName="other", displayName="Other"),
            ]
        )
        db.commit()
    finally:
        db.close()

    owner = signed_client_factory("owner")
    saved = owner.post(
        "/agent/daily-summary",
        headers=_agent_headers("owner"),
        json={
            "reportDate": "2026-07-19",
            "stat": "complete",
            "content": "**Completed**\n- Finished the report",
        },
    )
    assert saved.status_code == 200
    assert saved.json()["data"]["reportDate"] == "2026-07-19"

    db = SessionLocal()
    try:
        store_daily_summary(
            db,
            user_id="other",
            report_date="2026-07-19",
            stat="complete",
            content="Private other-user report",
        )
    finally:
        db.close()

    reports = owner.get("/api/daily-summaries", params={"date": "2026-07-19"})
    assert reports.status_code == 200
    assert [row["content"] for row in reports.json()["data"]] == [
        "**Completed**\n- Finished the report"
    ]
    assert owner.get(
        "/api/daily-summaries",
        params={"date": "2026-07-19", "text": "finished"},
    ).json()["data"]
    assert (
        owner.get(
            "/api/daily-summaries",
            params={"date": "2026-07-19", "text": "Private other-user"},
        ).json()["data"]
        == []
    )


def test_scheduler_dispatches_once_per_bound_user_and_records_failures(app_env) -> None:
    create_app()
    db = SessionLocal()
    try:
        db.add_all(
            [
                AppUser(userId="bound", loginName="bound", displayName="Bound"),
                AppUser(userId="unbound", loginName="unbound", displayName="Unbound"),
            ]
        )
        db.flush()
        db.add(
            FeishuBot(
                botId="bot-bound",
                userId="bound",
                botName="Bot",
                appId="app-bound",
                appSecretCipher="secret",
                verificationTokenCipher="verify",
                encryptKeyCipher="encrypt",
                enabled=True,
            )
        )
        db.add(
            LifeIdentity(
                identityId="identity-bound",
                userId="bound",
                provider="feishu",
                externalId="open-bound",
            )
        )
        db.flush()
        db.add(
            FeishuBind(
                bindId="bind-bound",
                userId="bound",
                botId="bot-bound",
                identityId="identity-bound",
                chatId="chat-bound",
                stat="active",
                isPrimary=True,
            )
        )
        db.commit()

        events: list[dict] = []
        settings = Settings(
            daily_summary_enabled=True,
            daily_summary_hour=22,
            daily_summary_timezone="Asia/Shanghai",
        )
        now = datetime(2026, 7, 19, 22, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        first = dispatch_daily_summaries(
            db,
            settings=settings,
            now=now,
            post_event=events.append,
        )
        assert first == {"queued": 1, "skipped": 0, "failed": 0}
        assert events[0]["event_type"] == "daily_summary"
        assert events[0]["reportDate"] == "2026-07-19"
        assert "agentScope" in events[0]
        assert dispatch_daily_summaries(
            db,
            settings=settings,
            now=now,
            post_event=events.append,
        ) == {"queued": 0, "skipped": 1, "failed": 0}
        assert len(events) == 1

        next_day = datetime(2026, 7, 20, 22, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

        def fail(_event: dict) -> None:
            raise RuntimeError("adapter unavailable")

        failed = dispatch_daily_summaries(
            db,
            settings=settings,
            now=next_day,
            post_event=fail,
        )
        assert failed == {"queued": 0, "skipped": 0, "failed": 1}
        row = db.scalar(
            select(DailySummary).where(
                DailySummary.userId == "bound",
                DailySummary.reportDate == "2026-07-20",
            )
        )
        assert row is not None and row.stat == "failed"
        assert "RuntimeError" in str(row.errorMessage)
    finally:
        db.close()


def test_scheduler_registers_daily_cron_at_configured_hour(app_env) -> None:
    class FakeScheduler:
        def __init__(self) -> None:
            self.jobs: list[tuple[object, dict]] = []
            self.started = False

        def add_job(self, function, **kwargs) -> None:
            self.jobs.append((function, kwargs))

        def start(self) -> None:
            self.started = True

    fake = FakeScheduler()
    service = SchedulerService(
        settings=Settings(
            scheduler_enabled=False,
            daily_summary_enabled=True,
            daily_summary_hour=22,
            daily_summary_timezone="Asia/Shanghai",
        ),
        session_factory=SessionLocal,
        scheduler=fake,  # type: ignore[arg-type]
    )
    service.start()
    assert fake.started is True
    assert len(fake.jobs) == 1
    assert fake.jobs[0][1] == {
        "trigger": "cron",
        "hour": 22,
        "minute": 0,
        "timezone": "Asia/Shanghai",
        "id": "smartcore-daily-summary",
        "replace_existing": True,
        "coalesce": True,
        "max_instances": 1,
        "misfire_grace_time": 300,
    }


def test_adapter_saves_daily_report_before_delivering(tmp_path, monkeypatch) -> None:
    calls: list[tuple[str, str]] = []
    report = (
        "内部分析不应发送\n"
        "📅 **2026年07月19日 工作日报**\n\n"
        "### 📝 本日工作概述\n> 完成核心工作。\n\n"
        "### 🚀 今日主要成果与技术进展\n- **项目**\n  - **进展**：完成工作。\n  - **技术要点/避坑**：记录中未提供技术细节。\n\n"
        "### ⚠️ 遇到问题与阻碍 (Blockers)\n- 今日记录中未发现明确阻碍。\n\n"
        "### 📅 明日规划\n- 继续已记录事项。"
    )
    payload = json.dumps({"result": {"finalAssistantVisibleText": report}})
    monkeypatch.setattr(
        adapter.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout=payload,
            stderr="",
        ),
    )
    monkeypatch.setattr(
        adapter,
        "save_daily_summary",
        lambda event, **kwargs: calls.append(("save", str(kwargs["content"]))),
    )
    monkeypatch.setattr(
        adapter,
        "deliver_reply",
        lambda event, text: calls.append(("deliver", text)) or True,
    )
    monkeypatch.setattr(adapter, "log", lambda *args, **kwargs: None)
    monkeypatch.setenv("OPENCLAW_WORKSPACE", str(tmp_path))

    event = {
        "event_id": "daily-summary:owner:2026-07-19",
        "event_type": "daily_summary",
        "reportDate": "2026-07-19",
        "agentScope": "signed",
        "chat_id": "chat-owner",
    }
    adapter.run_openclaw(event)

    assert calls == [
        ("save", report[report.index("📅") :]),
        ("deliver", report[report.index("📅") :]),
    ]
    prompt = adapter.build_prompt(event)
    assert "不加状态过滤" in prompt
    assert "禁止输出分析过程" in prompt


def test_adapter_retries_invalid_daily_report_in_isolated_session(tmp_path, monkeypatch) -> None:
    report = (
        "📅 **2026年07月19日 工作日报**\n\n"
        "### 📝 本日工作概述\n> 完成核心工作。\n\n"
        "### 🚀 今日主要成果与技术进展\n- **项目**\n  - **进展**：完成工作。\n  - **技术要点/避坑**：记录中未提供技术细节。\n\n"
        "### ⚠️ 遇到问题与阻碍 (Blockers)\n- 今日记录中未发现明确阻碍。\n\n"
        "### 📅 明日规划\n- 继续已记录事项。"
    )
    outputs = iter(
        [
            json.dumps({"result": {"finalAssistantVisibleText": "Analysis only"}}),
            json.dumps({"result": {"finalAssistantVisibleText": report}}),
        ]
    )
    sessions: list[str] = []

    def fake_run(args, **_kwargs):
        sessions.append(args[args.index("--session-key") + 1])
        return SimpleNamespace(returncode=0, stdout=next(outputs), stderr="")

    saved: list[str] = []
    monkeypatch.setattr(adapter.subprocess, "run", fake_run)
    monkeypatch.setattr(
        adapter,
        "save_daily_summary",
        lambda _event, **kwargs: saved.append(str(kwargs["content"])),
    )
    monkeypatch.setattr(adapter, "deliver_reply", lambda *_args: True)
    monkeypatch.setattr(adapter, "log", lambda *_args, **_kwargs: None)
    monkeypatch.setenv("OPENCLAW_WORKSPACE", str(tmp_path))

    adapter.run_openclaw(
        {
            "event_id": "daily-summary:owner:2026-07-19",
            "event_type": "daily_summary",
            "reportDate": "2026-07-19",
            "agentScope": "signed",
            "chat_id": "chat-owner",
        }
    )

    assert saved == [report]
    assert len(sessions) == 2
    assert sessions[0] != sessions[1]
    assert sessions[1].endswith("-format-retry")


def _payload() -> dict:
    hours = [f"2026-07-20T{hour:02d}:00" for hour in range(24)]
    return {
        "hourly": {
            "time": hours,
            "temperature_2m": [30.0] * 24,
            "apparent_temperature": [32.0] * 24,
            "precipitation_probability": [20] * 24,
            "weather_code": [1] * 24,
            "wind_speed_10m": [8.0] * 24,
        },
        "daily": {
            "time": ["2026-07-20", "2026-07-21"],
            "weather_code": [1, 61],
            "temperature_2m_max": [34.0, 33.0],
            "temperature_2m_min": [27.0, 26.0],
            "precipitation_probability_max": [30, 80],
            "sunrise": ["2026-07-20T05:10", "2026-07-21T05:11"],
            "sunset": ["2026-07-20T18:58", "2026-07-21T18:58"],
        },
    }


def _response(payload: dict, status_code: int = 200) -> httpx.Response:
    request = httpx.Request("GET", "https://api.open-meteo.com/v1/forecast")
    return httpx.Response(status_code, request=request, json=payload)


def test_weather_refresh_normalizes_and_preserves_stale_cache(app_env) -> None:
    create_app()
    db = SessionLocal()
    settings = Settings(weather_enabled=True)
    try:
        result = refresh_weather(
            db,
            settings=settings,
            request=lambda *args, **kwargs: _response(_payload()),
        )
        assert result["location"]["name"] == "杭州市钱塘区"
        assert len(result["hours"]) == 24
        assert result["days"][1]["temperatureMax"] == 33.0
        assert result["stale"] is False

        stale = refresh_weather(
            db,
            settings=settings,
            request=lambda *args, **kwargs: _response({}, 503),
        )
        assert len(stale["hours"]) == 24
        assert stale["stale"] is True
        assert "HTTPStatusError" in stale["errorMessage"]
    finally:
        db.close()


def test_weather_api_requires_login_and_returns_cached_forecast(
    app_env,
    client,
    signed_client_factory,
) -> None:
    db = SessionLocal()
    try:
        db.add(AppUser(userId="owner", loginName="owner", displayName="Owner"))
        db.commit()
        refresh_weather(
            db,
            settings=Settings(weather_enabled=True),
            request=lambda *args, **kwargs: _response(_payload()),
        )
    finally:
        db.close()

    assert client.get("/api/weather").status_code == 401
    owner = signed_client_factory("owner")
    response = owner.get("/api/weather")
    assert response.status_code == 200
    assert response.json()["data"]["hours"][0]["weatherCode"] == 1


def test_tomorrow_weather_is_sent_once_per_bound_user(app_env, monkeypatch) -> None:
    create_app()
    db = SessionLocal()
    try:
        db.add(AppUser(userId="owner", loginName="owner", displayName="Owner"))
        db.add(
            FeishuBot(
                botId="bot-owner",
                userId="owner",
                botName="Bot",
                appId="app",
                appSecretCipher="cipher",
                verificationTokenCipher="cipher",
                encryptKeyCipher="cipher",
                enabled=True,
                isDefault=True,
            )
        )
        db.add(
            LifeIdentity(
                identityId="identity-owner",
                userId="owner",
                provider="feishu",
                externalId="open-owner",
            )
        )
        db.flush()
        db.add(
            FeishuBind(
                bindId="bind-owner",
                userId="owner",
                botId="bot-owner",
                identityId="identity-owner",
                chatId="chat-owner",
                stat="active",
                isPrimary=True,
            )
        )
        db.commit()
        refresh_weather(
            db,
            settings=Settings(weather_enabled=True),
            request=lambda *args, **kwargs: _response(_payload()),
        )

        monkeypatch.setattr(
            "app.server.new_core.notify._sendFeishu",
            lambda db, title, content, *, userId: (True, "chat-owner", None),
        )
        now = datetime(2026, 7, 20, 22, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        first = deliver_tomorrow_weather(
            db,
            settings=Settings(weather_enabled=True),
            now=now,
            refresh=False,
        )
        second = deliver_tomorrow_weather(
            db,
            settings=Settings(weather_enabled=True),
            now=now,
            refresh=False,
        )
        assert first == {"sent": 1, "skipped": 0, "failed": 0}
        assert second == {"sent": 0, "skipped": 1, "failed": 0}
        assert get_weather(db)["days"][1]["date"] == "2026-07-21"
    finally:
        db.close()


def test_scheduler_registers_weather_and_daily_summary_at_2359(app_env) -> None:
    class FakeScheduler:
        def __init__(self) -> None:
            self.jobs: list[tuple[object, dict]] = []

        def add_job(self, function, **kwargs) -> None:
            self.jobs.append((function, kwargs))

        def start(self) -> None:
            pass

    fake = FakeScheduler()
    service = SchedulerService(
        settings=Settings(
            scheduler_enabled=False,
            daily_summary_enabled=True,
            daily_summary_hour=23,
            daily_summary_minute=59,
            weather_enabled=True,
            weather_refresh_minutes=30,
            weather_daily_hour=22,
            weather_daily_minute=0,
        ),
        session_factory=SessionLocal,
        scheduler=fake,  # type: ignore[arg-type]
    )
    service.start()
    jobs = {kwargs["id"]: kwargs for _, kwargs in fake.jobs}
    assert jobs["smartcore-daily-summary"]["hour"] == 23
    assert jobs["smartcore-daily-summary"]["minute"] == 59
    assert jobs["smartcore-weather-refresh"]["minutes"] == 30
    assert jobs["smartcore-weather-daily"]["hour"] == 22
    assert jobs["smartcore-weather-daily"]["minute"] == 0
