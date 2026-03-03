from pathlib import Path
from typing import Dict

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Home Assistant
    ha_base_url: str = "http://localhost:8123"
    ha_token: str = ""

    # App
    # TODO(auth): add secret_key: str here when implementing session/cookie auth
    debug: bool = False

    # Layout persistence
    layout_file: Path = DATA_DIR / "layout.json"

    @property
    def ha_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.ha_token}",
            "Content-Type": "application/json",
        }


settings = Settings()
