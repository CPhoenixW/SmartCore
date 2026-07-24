from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.server.config import Settings
from app.server.new_core.models import AppUser, FeishuBind, FeishuBot, WeatherForecast
from app.server.new_core.notify import sendReminder

LOCATION_KEY = "hangzhou-qiantang"


def _iso_now(timezone: str) -> str:
    return datetime.now(ZoneInfo(timezone)).replace(microsecond=0).isoformat()


def _series(payload: dict[str, Any], group: str, key: str) -> list[Any]:
    values = payload.get(group)
    if not isinstance(values, dict) or not isinstance(values.get(key), list):
        raise ValueError(f"weather response missing {group}.{key}")
    return values[key]


def _normalize(payload: dict[str, Any], settings: Settings) -> dict[str, Any]:
    hourly_times = _series(payload, "hourly", "time")
    hourly_keys = {
        "temperature": "temperature_2m",
        "apparentTemperature": "apparent_temperature",
        "precipitationProbability": "precipitation_probability",
        "weatherCode": "weather_code",
        "windSpeed": "wind_speed_10m",
    }
    hourly_values = {
        output: _series(payload, "hourly", source)
        for output, source in hourly_keys.items()
    }
    if not hourly_times:
        raise ValueError("weather response has no hourly forecast")
    if any(len(values) != len(hourly_times) for values in hourly_values.values()):
        raise ValueError("weather hourly series lengths differ")

    daily_dates = _series(payload, "daily", "time")
    daily_keys = {
        "weatherCode": "weather_code",
        "temperatureMax": "temperature_2m_max",
        "temperatureMin": "temperature_2m_min",
        "precipitationProbabilityMax": "precipitation_probability_max",
        "sunrise": "sunrise",
        "sunset": "sunset",
    }
    daily_values = {
        output: _series(payload, "daily", source)
        for output, source in daily_keys.items()
    }
    if any(len(values) != len(daily_dates) for values in daily_values.values()):
        raise ValueError("weather daily series lengths differ")

    return {
        "location": {
            "key": LOCATION_KEY,
            "name": settings.weather_location_name,
            "latitude": settings.weather_latitude,
            "longitude": settings.weather_longitude,
        },
        "timezone": settings.weather_timezone,
        "hours": [
            {
                "time": time,
                **{
                    output: hourly_values[output][index]
                    for output in hourly_keys
                },
            }
            for index, time in enumerate(hourly_times)
        ],
        "days": [
            {
                "date": date,
                **{
                    output: daily_values[output][index]
                    for output in daily_keys
                },
            }
            for index, date in enumerate(daily_dates)
        ],
    }


def refresh_weather(
    db: Session,
    *,
    settings: Settings,
    request: Callable[..., httpx.Response] | None = None,
) -> dict[str, Any]:
    attempted_at = _iso_now(settings.weather_timezone)
    row = db.get(WeatherForecast, LOCATION_KEY)
    if row is None:
        row = WeatherForecast(
            locationKey=LOCATION_KEY,
            locationName=settings.weather_location_name,
            latitude=settings.weather_latitude,
            longitude=settings.weather_longitude,
            timezone=settings.weather_timezone,
            lastAttemptAt=attempted_at,
        )
        db.add(row)
    row.lastAttemptAt = attempted_at
    try:
        fetch = request or httpx.get
        response = fetch(
            settings.weather_api_url,
            params={
                "latitude": settings.weather_latitude,
                "longitude": settings.weather_longitude,
                "hourly": (
                    "temperature_2m,apparent_temperature,"
                    "precipitation_probability,weather_code,wind_speed_10m"
                ),
                "daily": (
                    "weather_code,temperature_2m_max,temperature_2m_min,"
                    "precipitation_probability_max,sunrise,sunset"
                ),
                "forecast_hours": 24,
                "forecast_days": 2,
                "timezone": settings.weather_timezone,
            },
            timeout=10,
        )
        response.raise_for_status()
        normalized = _normalize(response.json(), settings)
        row.forecast = normalized
        row.fetchedAt = attempted_at
        row.errorMessage = None
    except Exception as exc:
        row.errorMessage = f"{type(exc).__name__}: {str(exc)[:300]}"
    db.commit()
    db.refresh(row)
    return weather_dict(row)


def weather_dict(row: WeatherForecast | None) -> dict[str, Any] | None:
    if row is None:
        return None
    forecast = dict(row.forecast or {})
    forecast.update(
        {
            "fetchedAt": row.fetchedAt,
            "lastAttemptAt": row.lastAttemptAt,
            "errorMessage": row.errorMessage,
            "stale": bool(row.errorMessage and row.forecast),
        }
    )
    return forecast


def get_weather(db: Session) -> dict[str, Any] | None:
    return weather_dict(db.get(WeatherForecast, LOCATION_KEY))


def _weather_label(code: Any) -> str:
    value = int(code)
    if value == 0:
        return "晴"
    if value in {1, 2, 3}:
        return "多云"
    if value in {45, 48}:
        return "有雾"
    if value in {51, 53, 55, 56, 57}:
        return "毛毛雨"
    if value in {61, 63, 65, 66, 67, 80, 81, 82}:
        return "有雨"
    if value in {71, 73, 75, 77, 85, 86}:
        return "有雪"
    if value in {95, 96, 99}:
        return "雷雨"
    return "天气变化"


def _primary_weather_users(db: Session) -> list[str]:
    return list(
        db.scalars(
            select(AppUser.userId)
            .join(FeishuBind, FeishuBind.userId == AppUser.userId)
            .join(FeishuBot, FeishuBot.botId == FeishuBind.botId)
            .where(
                AppUser.stat == "active",
                FeishuBind.stat == "active",
                FeishuBind.isPrimary.is_(True),
                FeishuBot.enabled.is_(True),
            )
            .distinct()
        ).all()
    )


def deliver_tomorrow_weather(
    db: Session,
    *,
    settings: Settings,
    now: datetime,
    refresh: bool = True,
) -> dict[str, int]:
    if refresh:
        refresh_weather(db, settings=settings)
    forecast = get_weather(db)
    result = {"sent": 0, "skipped": 0, "failed": 0}
    if not forecast:
        result["failed"] = len(_primary_weather_users(db))
        return result

    timezone = ZoneInfo(settings.weather_timezone)
    tomorrow = (now.astimezone(timezone) + timedelta(days=1)).date().isoformat()
    day = next(
        (item for item in forecast.get("days", []) if item.get("date") == tomorrow),
        None,
    )
    users = _primary_weather_users(db)
    if day is None:
        result["failed"] = len(users)
        return result

    title = f"明日天气 · {settings.weather_location_name}"
    content = (
        f"{tomorrow} {_weather_label(day['weatherCode'])}，"
        f"{round(float(day['temperatureMin']))}–{round(float(day['temperatureMax']))}°C，"
        f"最高降水概率 {round(float(day['precipitationProbabilityMax']))}%"
    )
    for user_id in users:
        delivery = sendReminder(
            db,
            evtId=None,
            title=title,
            content=content,
            channel="feishu",
            dedupKey=f"weather:tomorrow:{user_id}:{tomorrow}",
            phase="notice",
            userId=user_id,
        )
        stat = delivery.get("stat")
        if stat == "sent":
            result["sent"] += 1
        elif stat == "deduped":
            result["skipped"] += 1
        else:
            result["failed"] += 1
    return result
