from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

load_dotenv()


class Settings(BaseModel):
    """Application configuration loaded from environment variables."""

    bot_token: str = Field(alias="BOT_TOKEN")
    database_url: str = Field(alias="DATABASE_URL")

    model_config = ConfigDict(populate_by_name=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance."""

    try:
        return Settings()
    except Exception as exc:
        missing = []
        if not os.getenv("BOT_TOKEN"):
            missing.append("BOT_TOKEN")
        if not os.getenv("DATABASE_URL"):
            missing.append("DATABASE_URL")
        if missing:
            raise RuntimeError(
                "Missing required environment variables: " + ", ".join(missing)
            ) from exc
        raise


settings = get_settings()
BOT_TOKEN: str = settings.bot_token.strip()
DATABASE_URL: str = settings.database_url

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable must not be empty.")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable must not be empty.")
