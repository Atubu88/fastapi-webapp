from __future__ import annotations

import secrets
import string

from fastapi import APIRouter, HTTPException, Request
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


@router.get("/join", name="screen:join")
async def join_room(request: Request, code: str, name: str):
    room = room_manager.get_room(code)
    if room is None:
        raise HTTPException(status_code=404, detail="Комната не найдена")

    try:
        player = room_manager.add_player(code, name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return templates.TemplateResponse(
        "templates/join.html",
        {
            "request": request,
            "room_id": room.room_id,
            "player_name": player.name,
        },
    )
