from __future__ import annotations

import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from screen import screen_router
from routers.admin import add_quiz
from core.config import STATIC_DIR, TEMPLATES_DIR, get_bot_token
from routers.auth import router as auth_router
from routers.main_router import router as main_router  # 👈 главный интерфейс (index и выбор режима)

# ------------------ Инициализация приложения ------------------

app = FastAPI(title="Quiz Mini App")

# Подключаем статику и шаблоны
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Подключаем роутеры
app.include_router(auth_router)
app.include_router(main_router)
app.include_router(screen_router)
app.include_router(add_quiz.router)

# ------------------ Проверка Telegram токена ------------------

@app.on_event("startup")
async def startup_check():
    """При старте проверяем, что BOT_TOKEN рабочий"""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"https://api.telegram.org/bot{get_bot_token()}/getMe")
        print("✅ Startup getMe:", r.text)
    except Exception as e:
        print("⚠️ Startup getMe error:", repr(e))


# ------------------ Точка входа ------------------

# Запуск в режиме разработки:
# uvicorn main:app --reload
