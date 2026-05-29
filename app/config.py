from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    app_name: str = "SmartCore"
    debug: bool = False
    database_url: str = f"sqlite:///{PROJECT_ROOT / 'data' / 'smartcore.sqlite'}"

    @property
    def database_path(self) -> Path:
        if self.database_url.startswith("sqlite:///"):
            return Path(self.database_url.removeprefix("sqlite:///"))
        return PROJECT_ROOT / "data" / "smartcore.sqlite"


@lru_cache
def get_settings() -> Settings:
    return Settings()
