from datetime import date
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    app_name: str = "SmartCore"
    debug: bool = False
    database_url: str = f"sqlite:///{PROJECT_ROOT / 'data' / 'smartcore.sqlite'}"

    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_verification_token: str = ""
    feishu_encrypt_key: str = ""
    feishu_default_chat_id: str = ""
    feishu_replay_max_age_seconds: int = 300
    semester_start: date | None = None

    llm_provider: str = ""
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-chat"
    dashboard_base_url: str = ""

    scheduler_enabled: bool = False
    scheduler_interval_seconds: int = 60

    agent_api_token: str = ""
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
