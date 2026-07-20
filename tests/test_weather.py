from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from fastapi.testclient import TestClient

from app.auth.security import create_session_token
from app.config import Settings
from app.db.session import SessionLocal
from app.main import create_app
from app.new_core.models import AppUser, FeishuBind, FeishuBot, LifeIdentity
from app.scheduler.service import SchedulerService
from app.weather.service import deliver_tomorrow_weather, get_weather, refresh_weather


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


def test_weather_api_requires_login_and_returns_cached_forecast(app_env) -> None:
    app = create_app()
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

    anonymous = TestClient(app)
    assert anonymous.get("/api/weather").status_code == 401
    owner = TestClient(app)
    owner.cookies.set("smartcore_session", create_session_token("owner"))
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
            "app.new_core.notify._sendFeishu",
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
