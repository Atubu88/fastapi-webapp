from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
import os
import secrets
import string
from typing import Any, TYPE_CHECKING

from fastapi import (
    APIRouter,
    Form,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from core.config import BASE_DIR
from services.quiz_service import get_quiz_details, list_quizzes
from .manager import room_manager

if TYPE_CHECKING:  # pragma: no cover - только для подсказок типов
    from .manager import Room

router = APIRouter(prefix="/screen", tags=["screen"])
templates = Jinja2Templates(directory=BASE_DIR / "templates")

BOT_USERNAME = os.getenv("BOT_USERNAME", "victorina2024_bot")
logger = logging.getLogger(__name__)


def _generate_room_id(length: int = 6) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _build_join_url(room_id: str) -> str:
    return f"https://t.me/{BOT_USERNAME}?startapp=join_{room_id}"


async def _preload_room_questions(room_id: str, quiz_id: int) -> None:
    await room_manager.preload_room_questions(room_id)


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
async def create_room(
    request: Request,
    quiz_id: int = Form(...),
    start_mode: str = Form("manual"),
    auto_start_delay: str | None = Form(None),
) -> HTMLResponse:
    quiz = await asyncio.to_thread(get_quiz_details, quiz_id)
    if quiz is None:
        raise HTTPException(status_code=404, detail="Викторина не найдена")

    room_id = _generate_room_id()
    room = room_manager.create_room(room_id, quiz_id=quiz_id)

    quiz_title = quiz.get("title") if isinstance(quiz, dict) else None
    if quiz_title:
        room.metadata["quiz_title"] = quiz_title

    asyncio.create_task(_preload_room_questions(room_id, quiz_id))

    start_mode_normalized = (start_mode or "manual").strip().lower()
    delay_seconds: int | None = None
    start_at: datetime | None = None
    if start_mode_normalized in {"auto", "scheduled"}:
        if auto_start_delay not in {None, ""}:
            try:
                delay_seconds = int(auto_start_delay)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                logger.warning(
                    "Invalid auto start delay provided",
                    extra={"room_id": room_id, "delay": auto_start_delay},
                )
        if delay_seconds is None:
            delay_seconds = 0
        if delay_seconds < 0:
            logger.warning(
                "Negative auto start delay ignored",
                extra={"room_id": room_id, "delay": delay_seconds},
            )
            delay_seconds = None
        else:
            start_at = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)

    auto_start_context: dict[str, Any] | None = None
    if start_at is not None:
        try:
            await room_manager.schedule_auto_start(
                room_id, start_at, origin="create_room"
            )
        except ValueError:
            logger.exception(
                "Failed to schedule auto start",
                extra={"room_id": room_id, "start_at": start_at.isoformat()},
            )
        else:
            now_iso = datetime.now(timezone.utc).isoformat()
            auto_start_context = {
                "scheduled_at": start_at.isoformat(),
                "delay": delay_seconds or 0,
                "origin": "create_room",
                "server_time": now_iso,
            }

    join_url = _build_join_url(room_id)
    context: dict[str, Any] = {
        "request": request,
        "room_id": room_id,
        "join_url": join_url,
        "quiz": quiz,
    }
    if auto_start_context is not None:
        context["auto_start"] = auto_start_context
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


async def _resolve_quiz_title(room: Room | None) -> str | None:
    if room is None:
        return None

    quiz_title = room.metadata.get("quiz_title")
    if quiz_title:
        return quiz_title

    if room.quiz_id is None:
        return None

    quiz = await asyncio.to_thread(get_quiz_details, room.quiz_id)
    if not quiz:
        return None

    quiz_title = quiz.get("title")
    if quiz_title:
        room.metadata["quiz_title"] = quiz_title
    return quiz_title


@router.get("/join", response_class=HTMLResponse, name="screen:join")
async def join_room_get(request: Request, code: str) -> HTMLResponse:
    room = room_manager.get_room(code)
    if room is None:
        raise HTTPException(status_code=404, detail="Комната не найдена")

    quiz_title = await _resolve_quiz_title(room)

    return templates.TemplateResponse(
        "screen/join_form.html",
        {"request": request, "room_id": code, "quiz_title": quiz_title},
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

    quiz_title = await _resolve_quiz_title(room)

    return templates.TemplateResponse(
        "screen/join.html",
        {
            "request": request,
            "room_id": room.room_id,
            "player_name": player.name,
            "quiz_title": quiz_title,
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
            room = room_manager.get_room(room_id)

            if action == "start_game":
                if room is None:
                    await websocket.send_json(
                        {
                            "event": "error",
                            "payload": {"message": "Комната не найдена."},
                        }
                    )
                    continue
                await room_manager.cancel_auto_start(
                    room_id, origin="host_manual_start", reason="manual_start"
                )
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
                    questions = await room_manager.ensure_questions_loaded(room)
                except ValueError:
                    await websocket.send_json(
                        {
                            "event": "error",
                            "payload": {
                                "message": "Для комнаты не выбрана викторина.",
                            },
                        }
                    )
                    continue
                except Exception:
                    await websocket.send_json(
                        {
                            "event": "error",
                            "payload": {
                                "message": "Не удалось загрузить вопросы викторины.",
                            },
                        }
                    )
                    continue

                if not questions:
                    await websocket.send_json(
                        {
                            "event": "error",
                            "payload": {
                                "message": "В выбранной викторине нет вопросов.",
                            },
                        }
                    )
                    continue

                await room_manager.start_game(room_id, questions)

            elif action == "show_question":
                await room_manager.show_next_question(room_id)
            elif action == "cancel_auto_start":
                await room_manager.cancel_auto_start(
                    room_id,
                    origin=message.get("origin") or "host",
                    reason=message.get("reason"),
                )
            elif action == "schedule_auto_start":
                start_at_iso = message.get("start_at")
                delay_value = message.get("delay")
                start_at: datetime | None = None

                if isinstance(start_at_iso, str) and start_at_iso:
                    try:
                        parsed = datetime.fromisoformat(start_at_iso)
                    except ValueError:
                        parsed = None
                    if parsed is not None:
                        if parsed.tzinfo is None:
                            parsed = parsed.replace(tzinfo=timezone.utc)
                        else:
                            parsed = parsed.astimezone(timezone.utc)
                        start_at = parsed

                if start_at is None:
                    try:
                        delay_seconds = int(delay_value)
                    except (TypeError, ValueError):
                        await websocket.send_json(
                            {
                                "event": "error",
                                "payload": {
                                    "message": "Не удалось запланировать автозапуск.",
                                },
                            }
                        )
                        continue
                    if delay_seconds < 0:
                        await websocket.send_json(
                            {
                                "event": "error",
                                "payload": {
                                    "message": "Задержка автозапуска не может быть отрицательной.",
                                },
                            }
                        )
                        continue
                    start_at = datetime.now(timezone.utc) + timedelta(
                        seconds=delay_seconds
                    )

                try:
                    await room_manager.schedule_auto_start(
                        room_id,
                        start_at,
                        origin=message.get("origin") or "host",
                    )
                except ValueError as exc:
                    await websocket.send_json(
                        {
                            "event": "error",
                            "payload": {"message": str(exc)},
                        }
                    )
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
