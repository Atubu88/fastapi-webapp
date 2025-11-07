from __future__ import annotations
from pathlib import Path
from functools import lru_cache
import os

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


# === Загрузка .env из корня проекта ===
env_path = Path(__file__).resolve().parent.parent / ".env"
print("🔍 Loading .env from:", env_path)

if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    print("⚠️  Warning: .env file not found at", env_path)


# === Настройки ===
class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""
    bot_token: str | None = None
    database_url: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()


settings = get_settings()

# === Отладочная информация ===
print("🔍 [CONFIG] BOT_TOKEN loaded:", bool(settings.bot_token))
print("🔍 [CONFIG] DATABASE_URL =", settings.database_url)


# === Проверка обязательных переменных ===
def _require_setting(value: str | None, env_name: str, *, strip: bool = False) -> str:
    """Return a required environment variable or raise a RuntimeError."""
    if value is None:
        raise RuntimeError(f"Missing required environment variable: {env_name}")

    processed = value.strip() if strip else value
    if not processed:
        raise RuntimeError(f"{env_name} environment variable must not be empty.")
    return processed


def get_bot_token() -> str:
    """Return the configured Telegram bot token.

    Falls back to a dummy value for local testing if BOT_TOKEN is missing.
    """
    value = settings.bot_token
    if not value or not value.strip():
        print("⚠️  BOT_TOKEN not set. Using placeholder for local testing.")
        return "placeholder"
    return value.strip()


def get_database_url() -> str:
    """Return the configured database connection string."""
    return _require_setting(settings.database_url, "DATABASE_URL")
