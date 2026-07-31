from datetime import date
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    app_name: str = "SmartCore"
    debug: bool = False
    database_url: str = f"sqlite:///{PROJECT_ROOT / 'data' / 'smartcore.sqlite'}"

    auth_secret: str = ""
    auth_secret_file: str = str(PROJECT_ROOT / "data" / "auth_secret")
    auth_cookie_name: str = "smartcore_session"
    auth_cookie_secure: bool = False
    auth_session_hours: int = 168

    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_verification_token: str = ""
    feishu_encrypt_key: str = ""
    feishu_default_chat_id: str = ""
    feishu_replay_max_age_seconds: int = 300
    semester_start: date | None = None

    llm_provider: str = "tokendance"
    llm_api_key: str = ""
    llm_base_url: str = "https://tokendance.space/gateway/v1"
    llm_model: str = "deepseek-v4-flash"
    llm_max_retries: int = 2
    llm_timeout_seconds: int = 120
    # Images are analyzed separately before the resulting text is handed to the
    # text-first SmartCore agent workflow.
    vision_model: str = "deepseek-ocr-2"
    vision_max_image_bytes: int = 10 * 1024 * 1024
    vision_max_output_tokens: int = 128
    vision_max_retries: int = 0
    vision_timeout_seconds: int = 60
    idea_media_dir: str = str(PROJECT_ROOT / "data" / "idea_media")
    idea_media_max_bytes: int = 20 * 1024 * 1024

    deepseek_api_key: str = ""
    deepseek_base_url: str = ""

    dashboard_base_url: str = ""

    scheduler_enabled: bool = False
    scheduler_interval_seconds: int = 60
    daily_summary_enabled: bool = False
    daily_summary_hour: int = 23
    daily_summary_minute: int = 59
    daily_summary_timezone: str = "Asia/Shanghai"
    computer_analysis_enabled: bool = False
    computer_analysis_timezone: str = "Asia/Shanghai"
    computer_analysis_minute: int = 5
    computer_work_block_analysis_enabled: bool = False
    computer_analysis_direct_llm_enabled: bool = True
    computer_analysis_model: str = "deepseek-v4-flash"
    computer_analysis_max_output_tokens: int = 2048
    computer_analysis_repair_attempts: int = 1
    computer_analysis_openclaw_fallback_enabled: bool = True
    computer_daily_preview_min_interval_minutes: int = 60

    weather_enabled: bool = False
    weather_refresh_minutes: int = 30
    weather_daily_hour: int = 22
    weather_daily_minute: int = 0
    weather_timezone: str = "Asia/Shanghai"
    weather_location_name: str = "杭州市钱塘区"
    weather_latitude: float = 30.284
    weather_longitude: float = 120.493
    weather_api_url: str = "https://api.open-meteo.com/v1/forecast"

    agent_api_token: str = ""
    device_api_token: str = ""
    device_heartbeat_interval_seconds: int = 10
    device_photo_request_ttl_seconds: int = 300
    device_photo_max_bytes: int = 10 * 1024 * 1024
    device_photo_dir: str = str(PROJECT_ROOT / "data" / "device_photos")
    computer_activity_retention_days: int = 90
    openclaw_events_endpoint: str = ""
    openclaw_events_token: str = ""

    backup_dir: str = str(PROJECT_ROOT / "backups")
    pi_user: str = ""
    pi_host: str = ""
    pi_backup_dir: str = ""
    local_backup_retention_days: int = 30
    pi_backup_retention_days: int = 90

    @property
    def database_path(self) -> Path:
        if self.database_url.startswith("sqlite:///"):
            return Path(self.database_url.removeprefix("sqlite:///"))
        return PROJECT_ROOT / "data" / "smartcore.sqlite"

    @property
    def backup_path(self) -> Path:
        return Path(self.backup_dir)

    @property
    def device_photo_path(self) -> Path:
        return Path(self.device_photo_dir)

    @property
    def idea_media_path(self) -> Path:
        return Path(self.idea_media_dir)


@lru_cache
def get_settings() -> Settings:
    return Settings()
