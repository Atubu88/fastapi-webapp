from __future__ import annotations

import secrets
import string

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
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


@router.websocket("/ws/host/{room_id}", name="screen:ws_host")
async def ws_host(websocket: WebSocket, room_id: str) -> None:
    room = room_manager.get_room(room_id)
    if room is None:
        await websocket.close(code=1008)
        return

    try:
        await websocket.accept()
        await room_manager.connect_screen(room_id, websocket)
    except ValueError:
        await websocket.close(code=1008)
        return

    try:
        while True:
            message = await websocket.receive_json()
            action = message.get("action")
            if action == "start_game":
                questions = message.get("questions") or []
                await room_manager.start_game(room_id, questions)
            elif action == "show_question":
                await room_manager.show_next_question(room_id)
            else:
                # Неизвестные действия игнорируются, но можно расширить обработку при необходимости.
                continue
    except WebSocketDisconnect:
        room_manager.disconnect_screen(room_id)
    finally:
        room_manager.disconnect_screen(room_id)


@router.websocket("/ws/player/{room_id}", name="screen:ws_player")
async def ws_player(websocket: WebSocket, room_id: str) -> None:
    room = room_manager.get_room(room_id)
    if room is None:
        await websocket.close(code=1008)
        return

    player_name = None

    try:
        await websocket.accept()
        while True:
            message = await websocket.receive_json()
            action = message.get("action")

            if action == "join":
                player_name = message.get("player")
                if not player_name:
                    await websocket.close(code=1008)
                    return
                try:
                    await room_manager.connect_player(room_id, player_name, websocket)
                except ValueError:
                    await websocket.close(code=1008)
                    return
            elif action == "answer" and player_name:
                answer = message.get("answer")
                await room_manager.submit_answer(room_id, player_name, answer)
            else:
                continue
    except WebSocketDisconnect:
        if player_name:
            room_manager.disconnect_player(room_id, player_name)
    finally:
        if player_name:
            room_manager.disconnect_player(room_id, player_name)
