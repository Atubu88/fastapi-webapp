from fastapi import APIRouter, HTTPException, Request
from fastapi.templating import Jinja2Templates

from core.config import ADMIN_ID, TEMPLATES_DIR
from core.telegram import validate_init_data

router = APIRouter(tags=["main"])
templates = Jinja2Templates(directory=TEMPLATES_DIR)

from fastapi.responses import RedirectResponse



import logging

def _extract_user_id(request: Request) -> int | None:
    logging.debug("🔍 Вызов _extract_user_id()")

    """Попытаться извлечь telegram_id пользователя из заголовков запроса."""

    header_candidates = (
        "X-Telegram-Web-App-Init-Data",
        "X-Telegram-Init-Data",
    )

    for header in header_candidates:
        init_data = request.headers.get(header)
        if not init_data:
            logging.debug(f"🔹 Header {header} отсутствует.")
            continue

        logging.debug(f"📦 Найден {header}: {init_data[:80]}...")  # первые 80 символов, чтобы не засорять логи

        try:
            payload = validate_init_data(init_data)
            logging.debug(f"✅ Валидация прошла успешно: {payload}")
        except HTTPException as e:
            logging.warning(f"⚠️ Ошибка валидации {header}: {e}")
            continue

        user = payload.get("user") or {}
        user_id = user.get("id")

        logging.debug(f"👤 Извлечён user_id={user_id}")

        if user_id is None:
            continue

        try:
            return int(user_id)
        except (TypeError, ValueError):
            logging.error(f"❌ Ошибка преобразования user_id={user_id} → int")
            continue

    logging.debug("🚫 Telegram ID не найден ни в одном заголовке.")
    return None


@router.get("/", name="index")
async def index(request: Request):
    """
    Отображает выбор режима или перенаправляет в комнату,
    если Mini App открыт по ссылке ?tgWebAppStartParam=join_<код>
    """
    # Telegram передаёт параметр как tgWebAppStartParam, а не startapp
    start_param = (
        request.query_params.get("startapp")
        or request.query_params.get("tgWebAppStartParam")
    )

    if start_param and start_param.startswith("join_"):
        code = start_param.replace("join_", "")
        return RedirectResponse(url=f"/screen/join?code={code}")

    modes = [
        {
            "id": "screen",
            "name": "🎬 Экранный режим",
            "desc": "Играем в одной комнате: вопросы на экране, ответы — с телефонов!"
        },
        {
            "id": "team",
            "name": "👥 Командный режим",
            "desc": "Создай команду и соревнуйся с другими!"
        },
        {
            "id": "solo",
            "name": "🧠 Одиночная игра",
            "desc": "Играй сам и побей свой рекорд!"
        },
    ]
    user_id = _extract_user_id(request)
    is_admin = bool(ADMIN_ID and user_id == ADMIN_ID)

    context = {
        "request": request,
        "modes": modes,
        "is_admin": is_admin,
    }

    return templates.TemplateResponse("index.html", context)
