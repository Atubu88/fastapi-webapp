from __future__ import annotations

import secrets
import string

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from core.config import BASE_DIR
from .manager import room_manager

router = APIRouter(prefix="/screen", tags=["screen"])
templates = Jinja2Templates(directory=BASE_DIR / "screen")


def _generate_room_id(length: int = 6) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


@router.get("", name="screen:index")
async def screen_index(request: Request):
    return templates.TemplateResponse(
        "templates/screen.html",
        {"request": request},
    )


@router.post("/create-room", name="screen:create_room")
async def create_room():
    room_id = _generate_room_id()
    room_manager.create_room(room_id)
    join_url = f"https://t.me/victorina2024_bot?startapp=join_{room_id}"
    return JSONResponse({"room_id": room_id, "join_url": join_url})
