from __future__ import annotations

import os
import secrets
import string
from typing import Any

from fastapi import APIRouter, Form, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from core.config import BASE_DIR
from services.quiz_service import get_quiz_details, get_quiz_questions, list_quizzes
from .manager import room_manager

router = APIRouter(prefix="/screen", tags=["screen"])
templates = Jinja2Templates(directory=BASE_DIR / "templates")

BOT_USERNAME = os.getenv("BOT_USERNAME", "victorina2024_bot")


def _generate_room_id(length: int = 6) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _build_join_url(room_id: str) -> str:
    return f"https://t.me/{BOT_USERNAME}?startapp=join_{room_id}"


@router.get("", name="screen:index")
async def screen_index() -> RedirectResponse:
    return RedirectResponse(url="/screen/create")


@router.get("/create", response_class=HTMLResponse, name="screen:create")
async def screen_create(request: Request) -> HTMLResponse:
    quizzes = list_quizzes()
    context: dict[str, Any] = {
        "request": request,
        "quizzes": quizzes,
    }
    return templates.TemplateResponse("screen/create.html", context)


@router.post("/create-room", response_class=HTMLResponse, name="screen:create_room")
async def create_room(request: Request, quiz_id: int = Form(...)) -> HTMLResponse:
    quiz = get_quiz_details(quiz_id)
    if quiz is None:
        raise HTTPException(status_code=404, detail="Викторина не найдена")

    room_id = _generate_room_id()
    room_manager.create_room(room_id, quiz_id=quiz_id)

    join_url = _build_join_url(room_id)
    context: dict[str, Any] = {
        "request": request,
        "room_id": room_id,
        "join_url": join_url,
        "quiz": quiz,
    }
    return templates.TemplateResponse("screen/room.html", context)


@router.get("/fragments/{state}", response_class=HTMLResponse, name="screen:fragment")
async def screen_fragment(request: Request, state: str) -> HTMLResponse:
    template_map: dict[str, str] = {
        "lobby": "screen/lobby.html",
        "question": "screen/question.html",
        "final": "screen/final.html",
    }

    template_name = template_map.get(state)
    if template_name is None:
        raise HTTPException(status_code=404, detail="Неизвестный экран")

    return templates.TemplateResponse(template_name, {"request": request})


@router.get("/join", response_class=HTMLResponse, name="screen:join")
async def join_room_get(request: Request, code: str) -> HTMLResponse:
    return templates.TemplateResponse(
        "screen/join_form.html",
        {"request": request, "room_id": code},
    )


@router.post("/join", response_class=HTMLResponse)
async def join_room_post(
    request: Request,
    code: str = Form(...),
    name: str = Form(...),
) -> HTMLResponse:
    room = room_manager.get_room(code)
    if room is None:
        raise HTTPException(status_code=404, detail="Комната не найдена")

    try:
        player = room_manager.add_player(code, name)
    except ValueError as exc:  # pragma: no cover - защитный код
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return templates.TemplateResponse(
        "screen/join.html",
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
                if room.quiz_id is None:
                    await websocket.send_json(
                        {
                            "event": "error",
                            "payload": {
                                "message": "Для комнаты не выбрана викторина."
                            },
                        }
                    )
                    continue

                try:
                    questions = get_quiz_questions(room.quiz_id)
                except Exception:
                    await websocket.send_json(
                        {
                            "event": "error",
                            "payload": {
                                "message": "Не удалось загрузить вопросы викторины."
                            },
                        }
                    )
                    continue

                if not questions:
                    await websocket.send_json(
                        {
                            "event": "error",
                            "payload": {
                                "message": "В выбранной викторине нет вопросов."
                            },
                        }
                    )
                    continue

                await room_manager.start_game(room_id, questions)
            elif action == "show_question":
                await room_manager.show_next_question(room_id)
            else:
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
