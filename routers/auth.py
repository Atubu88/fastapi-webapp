from __future__ import annotations
from typing import Any, Dict, Type, TypeVar
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel, Field
from core.telegram import validate_init_data

router = APIRouter(tags=["auth"])

TModel = TypeVar("TModel", bound=BaseModel)

class LoginRequest(BaseModel):
    init_data: str = Field(alias="initData")

def _is_json_request(request: Request) -> bool:
    return "application/json" in request.headers.get("content-type", "").lower()

async def _parse_request_payload(request: Request, model: Type[TModel]) -> TModel:
    ct = request.headers.get("content-type", "").split(";")[0].strip().lower()
    raw: Dict[str, Any]
    if ct == "application/json":
        raw = await request.json()
    else:
        form = await request.form()
        raw = dict(form)
    return model.model_validate(raw)

@router.post("/login", response_class=HTMLResponse)
async def login(request: Request) -> HTMLResponse:
    payload = await _parse_request_payload(request, LoginRequest)
    init_payload = validate_init_data(payload.init_data)

    # TODO: подключите вашу логику get_or_create_user(...)
    user_record = {
        "id": init_payload["user"]["id"],            # временно используем Telegram id
        "telegram_id": init_payload["user"]["id"],
        "username": init_payload["user"].get("username"),
        "first_name": init_payload["user"].get("first_name"),
        "last_name": init_payload["user"].get("last_name"),
    }

    if _is_json_request(request):
        return JSONResponse({"user": user_record, "redirect": "/"})

    # Вернём простую HTML-страницу (шаблон index.html должен существовать)
    from fastapi.templating import Jinja2Templates
    from core.config import TEMPLATES_DIR
    templates = Jinja2Templates(directory=TEMPLATES_DIR)
    context = {"request": request, "user": user_record, "login_success": True}
    return templates.TemplateResponse("index.html", context)
