from __future__ import annotations

from functools import lru_cache

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

load_dotenv()


class Settings(BaseModel):
    """Application configuration loaded from environment variables."""

    bot_token: str | None = Field(default=None, alias="BOT_TOKEN")
    database_url: str | None = Field(default=None, alias="DATABASE_URL")

    model_config = ConfigDict(populate_by_name=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance."""

    return Settings()


settings = get_settings()


def _require_setting(value: str | None, env_name: str, *, strip: bool = False) -> str:
    """Return a required environment variable or raise a RuntimeError."""

    if value is None:
        raise RuntimeError(f"Missing required environment variable: {env_name}")

    processed = value.strip() if strip else value
    if not processed:
        raise RuntimeError(f"{env_name} environment variable must not be empty.")

    return processed


def get_bot_token() -> str:
    """Return the configured Telegram bot token."""

    return _require_setting(settings.bot_token, "BOT_TOKEN", strip=True)


def get_database_url() -> str:
    """Return the configured database connection string."""

    return _require_setting(settings.database_url, "DATABASE_URL")
