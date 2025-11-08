from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from core.config import TEMPLATES_DIR

router = APIRouter(tags=["main"])
templates = Jinja2Templates(directory=TEMPLATES_DIR)


@router.get("/", name="index")
async def index(request: Request):
    """
    Отображает выбор режима викторины.
    Типы храним просто в коде — их немного.
    """
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
    return templates.TemplateResponse("index.html", {"request": request, "modes": modes})