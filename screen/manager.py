from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

import asyncio

DEFAULT_QUESTION_DURATION = 30

from fastapi import WebSocket
from starlette.websockets import WebSocketState


@dataclass
class Room:
    """Простая структура данных для хранения информации о комнате."""

    room_id: str
    quiz_id: int | None = None
    players: Dict[str, "Player"] = field(default_factory=dict)
    metadata: Dict[str, str] = field(default_factory=dict)
    events: List[tuple[str, dict | None]] = field(default_factory=list)
    screen: WebSocket | None = None
    sockets: Dict[str, WebSocket] = field(default_factory=dict)
    answers: Dict[str, str] = field(default_factory=dict)
    scores: Dict[str, int] = field(default_factory=dict)
    questions: List[dict] = field(default_factory=list)
    current_question_index: int = -1
    question_started_at: Optional[datetime] = None
    question_duration: Optional[int] = None
    question_timeout_task: Optional[asyncio.Task[None]] = None


@dataclass
class Player:
    """Игрок, подключённый к комнате."""

    name: str
    answered: bool = False
    score: int = 0


class ScreenRoomManager:
    """In-memory менеджер комнат экранного режима."""

    def __init__(self) -> None:
        self._rooms: Dict[str, Room] = {}

    def create_room(self, room_id: str, *, quiz_id: int | None = None) -> Room:
        room = Room(room_id=room_id, quiz_id=quiz_id)
        self._rooms[room_id] = room
        return room

    def get_room(self, room_id: str) -> Room | None:
        return self._rooms.get(room_id)

    def add_player(self, room_id: str, player_name: str) -> Player:
        room = self.get_room(room_id)
        if room is None:
            raise ValueError(f"Room '{room_id}' not found")

        player = room.players.get(player_name)
        if player is None:
            player = Player(name=player_name)
            room.players[player_name] = player
            room.scores[player_name] = 0
        return player

    def all_answered(self, room_id: str) -> bool:
        room = self.get_room(room_id)
        if room is None or not room.players:
            return False
        return all(player.answered for player in room.players.values())

    async def connect_screen(self, room_id: str, websocket: WebSocket) -> None:
        room = self.get_room(room_id)
        if room is None:
            raise ValueError(f"Room '{room_id}' not found")
        room.screen = websocket
        for event_name, payload in room.events:
            await self._send_json(websocket, event_name, payload)

    async def connect_player(self, room_id: str, player_name: str, websocket: WebSocket) -> Player:
        room = self.get_room(room_id)
        if room is None:
            raise ValueError(f"Room '{room_id}' not found")

        player = self.add_player(room_id, player_name)
        room.sockets[player_name] = websocket
        await self.notify_player_joined(room_id, player)

        # Если уже есть активный вопрос — отправляем его вновь подключившемуся игроку.
        if 0 <= room.current_question_index < len(room.questions):
            question_payload = self._build_question_payload(room)
            await self._send_json(websocket, "show_question", question_payload)
        return player

    def disconnect_screen(self, room_id: str) -> None:
        room = self.get_room(room_id)
        if room is None:
            return
        room.screen = None

    def disconnect_player(self, room_id: str, player_name: str) -> None:
        room = self.get_room(room_id)
        if room is None:
            return
        room.sockets.pop(player_name, None)

    async def broadcast(self, room_id: str, event: str, payload: Dict | None = None) -> None:
        room = self.get_room(room_id)
        if room is None:
            raise ValueError(f"Room '{room_id}' not found")

        room.events.append((event, payload))

        targets: list[WebSocket] = []
        if room.screen is not None:
            targets.append(room.screen)
        targets.extend(room.sockets.values())

        for websocket in list(targets):
            await self._send_json(websocket, event, payload)

    async def notify_player_joined(self, room_id: str, player: Player) -> None:
        room = self.get_room(room_id)
        if room is None:
            return

        payload = {
            "player": player.name,
            "players": sorted(room.players.keys()),
        }
        await self.broadcast(room_id, "player_joined", payload)

    async def start_game(self, room_id: str, questions: List[dict]) -> None:
        room = self.get_room(room_id)
        if room is None:
            raise ValueError(f"Room '{room_id}' not found")

        room.questions = questions
        room.current_question_index = -1
        room.answers.clear()
        room.events.clear()
        for player in room.players.values():
            player.score = 0
            player.answered = False
            room.scores[player.name] = 0

        await self.show_next_question(room_id)

    async def show_next_question(self, room_id: str) -> None:
        room = self.get_room(room_id)
        if room is None:
            return

        self._cancel_question_timer(room)
        room.current_question_index += 1
        room.answers.clear()
        for player in room.players.values():
            player.answered = False

        if room.current_question_index >= len(room.questions):
            room.question_started_at = None
            room.question_duration = None
            await self._broadcast_final(room)
            return

        question = room.questions[room.current_question_index]
        duration = self._extract_question_duration(question)
        room.question_duration = duration
        room.question_started_at = datetime.now(timezone.utc)
        payload = self._build_question_payload(room)
        await self.broadcast(room_id, "show_question", payload)

        if duration:
            room.question_timeout_task = asyncio.create_task(
                self._handle_question_timeout(room, duration)
            )

    async def submit_answer(self, room_id: str, player_name: str, answer: str) -> None:
        room = self.get_room(room_id)
        if room is None:
            raise ValueError(f"Room '{room_id}' not found")

        if player_name not in room.players:
            raise ValueError(f"Player '{player_name}' not registered in room '{room_id}'")

        room.answers[player_name] = answer
        player = room.players[player_name]
        player.answered = True

        if self.all_answered(room_id):
            await self._handle_all_answers(room)

    async def _handle_all_answers(self, room: Room) -> None:
        self._cancel_question_timer(room)
        payload = self._build_results_payload(room)
        await self.broadcast(room.room_id, "show_results", payload)
        await self.show_next_question(room.room_id)

    async def _broadcast_final(self, room: Room) -> None:
        self._cancel_question_timer(room)
        room.question_started_at = None
        room.question_duration = None
        scoreboard = self._build_scoreboard(room)
        payload = {"scoreboard": scoreboard}
        await self.broadcast(room.room_id, "show_final", payload)

    def _build_question_payload(self, room: Room) -> Dict:
        question = room.questions[room.current_question_index]
        total = len(room.questions)
        payload = {
            "question": {
                key: value
                for key, value in question.items()
                if key not in {"correct_option", "score"}
            },
            "question_number": room.current_question_index + 1,
            "total_questions": total,
        }
        if "options" in question:
            payload["question"]["options"] = question["options"]
        if room.question_started_at is not None:
            payload["question_started_at"] = room.question_started_at.isoformat()
        if room.question_duration is not None:
            payload["question_duration"] = room.question_duration
        return payload

    def _build_results_payload(self, room: Room) -> Dict:
        question = room.questions[room.current_question_index]
        correct_answer = question.get("correct_option")
        question_score = int(question.get("score", 1))

        results = []
        for player_name, player in room.players.items():
            answer = room.answers.get(player_name)
            is_correct = answer == correct_answer and answer is not None
            if is_correct:
                player.score += question_score
            results.append(
                {
                    "player": player_name,
                    "answer": answer,
                    "is_correct": is_correct,
                    "score": player.score,
                }
            )
            room.scores[player_name] = player.score

        payload = {
            "question_id": question.get("id"),
            "correct_answer": correct_answer,
            "results": results,
            "scoreboard": self._build_scoreboard(room),
        }
        if room.question_started_at is not None:
            payload["question_started_at"] = room.question_started_at.isoformat()
        if room.question_duration is not None:
            payload["question_duration"] = room.question_duration
        return payload

    def _build_scoreboard(self, room: Room) -> List[Dict[str, str | int]]:
        scoreboard = [
            {"player": player.name, "score": player.score}
            for player in room.players.values()
        ]
        scoreboard.sort(key=lambda item: (-int(item["score"]), item["player"]))
        return scoreboard

    async def _handle_question_timeout(self, room: Room, duration: int) -> None:
        try:
            await asyncio.sleep(duration)
            # Если вопрос уже сменился — ничего не делаем.
            if room.question_timeout_task is not asyncio.current_task():
                return

            for player in room.players.values():
                if not player.answered:
                    room.answers.setdefault(player.name, None)
                    player.answered = True

            payload = self._build_results_payload(room)
            await self.broadcast(room.room_id, "show_results", payload)
            await self.show_next_question(room.room_id)
        except asyncio.CancelledError:
            raise
        finally:
            if room.question_timeout_task is asyncio.current_task():
                room.question_timeout_task = None

    def _cancel_question_timer(self, room: Room) -> None:
        task = room.question_timeout_task
        if task is not None:
            current = asyncio.current_task()
            if task is not current:
                task.cancel()
        room.question_timeout_task = None

    def _extract_question_duration(self, question: Dict) -> Optional[int]:
        """Получить время на ответ в секундах из вопроса."""

        for key in ("timer", "time_limit", "duration", "question_duration"):
            raw_value = question.get(key)
            if raw_value is None:
                continue
            try:
                value = int(raw_value)
            except (TypeError, ValueError):
                continue
            if value > 0:
                return value
        return DEFAULT_QUESTION_DURATION

    async def _send_json(
        self, websocket: WebSocket | None, event: str, payload: Dict | None
    ) -> None:
        if websocket is None:
            return
        if websocket.application_state != WebSocketState.CONNECTED:
            return

        try:
            await websocket.send_json({"event": event, "payload": payload})
        except RuntimeError:
            # Соединение могло закрыться между проверками состояния и отправкой.
            pass


room_manager = ScreenRoomManager()
