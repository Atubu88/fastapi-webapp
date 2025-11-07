"""Compatibility module that exposes the FastAPI application instance."""

# ✅ Загружаем .env ДО импорта webapp.main
from dotenv import load_dotenv
from pathlib import Path

env_path = Path(__file__).resolve().parent / ".env"
print("🔄 Preloading .env before imports:", env_path)
load_dotenv(dotenv_path=env_path)

# ✅ Импорт приложения после загрузки переменных окружения
from webapp.main import app

__all__ = ["app"]
