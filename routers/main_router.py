from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from core.config import TEMPLATES_DIR, ADMIN_ID  # ✅ добавили ADMIN_ID

router = APIRouter(tags=["main"])
templates = Jinja2Templates(directory=TEMPLATES_DIR)


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

    # Получаем пользователя из сессии (если уже сохранён)
    user = request.session.get("user")

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

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "modes": modes,
            "user": user,
            "admin_id": ADMIN_ID,  # ✅ передаём ID администратора в шаблон
        },
    )
