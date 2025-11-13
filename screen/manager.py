from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

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
    scores: Dict[str, float] = field(default_factory=dict)
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
    score: float = 0.0
    last_answered_at: Optional[datetime] = None
    last_response_time: Optional[float] = None
    response_times: List[float] = field(default_factory=list)
    total_response_time: float = 0.0
    min_response_time: Optional[float] = None
    max_response_time: Optional[float] = None


class ScreenRoomManager:
    """In-memory менеджер комнат экранного режима."""

    def __init__(self) -> None:
        self._rooms: Dict[str, Room] = {}

    @staticmethod
    def _current_time_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

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
            room.scores[player_name] = 0.0
        self._ensure_player_tracking(player)
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

        # 🔥 Параллельная рассылка всем
        await asyncio.gather(
            *(self._send_json(ws, event, payload) for ws in targets),
            return_exceptions=True  # не прерывает, если один сокет уже закрылся
        )

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

        self._cancel_question_timer(room)
        room.questions = questions
        room.current_question_index = -1
        room.answers.clear()
        room.events.clear()
        room.question_started_at = None
        room.question_duration = None
        for player in room.players.values():
            self._ensure_player_tracking(player)
            player.score = 0.0
            player.answered = False
            player.last_answered_at = None
            player.last_response_time = None
            player.response_times.clear()
            player.total_response_time = 0.0
            player.min_response_time = None
            player.max_response_time = None
            room.scores[player.name] = 0.0

        await self.show_next_question(room_id)

    async def show_next_question(self, room_id: str) -> None:
        room = self.get_room(room_id)
        if room is None:
            return

        self._cancel_question_timer(room)
        room.current_question_index += 1
        room.answers.clear()
        for player in room.players.values():
            self._ensure_player_tracking(player)
            player.answered = False
            player.last_answered_at = None
            player.last_response_time = None

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

        player = room.players[player_name]
        self._ensure_player_tracking(player)
        if room.question_started_at is None:
            return
        if not (0 <= room.current_question_index < len(room.questions)):
            return
        if player.answered:
            return

        room.answers[player_name] = answer
        player.answered = True
        now = datetime.now(timezone.utc)
        player.last_answered_at = now
        response_time: Optional[float] = None
        if room.question_started_at is not None:
            response_time = (now - room.question_started_at).total_seconds()
        player.last_response_time = response_time
        if response_time is not None:
            if response_time < 0:
                response_time = 0.0
            if room.question_duration is not None:
                response_time = min(response_time, float(room.question_duration))
            response_time = float(response_time)
            player.response_times.append(response_time)
            player.total_response_time += response_time
            if (
                player.min_response_time is None
                or response_time < player.min_response_time
            ):
                player.min_response_time = response_time
            if (
                player.max_response_time is None
                or response_time > player.max_response_time
            ):
                player.max_response_time = response_time

        if self.all_answered(room_id):
            await self._handle_all_answers(room)

    async def _handle_all_answers(self, room: Room) -> None:
        self._cancel_question_timer(room)
        for player in room.players.values():
            self._ensure_player_tracking(player)
            if player.name not in room.answers:
                room.answers[player.name] = None
                if not player.answered:
                    player.last_response_time = None
        payload = self._build_results_payload(room)
        await self.broadcast(room.room_id, "show_results", payload)
        await self.show_next_question(room.room_id)

    async def _broadcast_final(self, room: Room) -> None:
        self._cancel_question_timer(room)
        room.question_started_at = None
        room.question_duration = None
        scoreboard = self._build_scoreboard(room)
        payload = {"scoreboard": scoreboard}
        payload["server_time"] = self._current_time_iso()
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
        payload["server_time"] = self._current_time_iso()
        return payload

    def _build_results_payload(self, room: Room) -> Dict:
        question = room.questions[room.current_question_index]
        correct_answer = question.get("correct_option")
        question_score = self._extract_question_score(question)

        results = []
        for player_name, player in room.players.items():
            answer = room.answers.get(player_name)
            is_correct = answer == correct_answer and answer is not None
            if is_correct:
                player.score = self._normalize_score(player.score + question_score)
            results.append(
                {
                    "player": player_name,
                    "answer": answer,
                    "is_correct": is_correct,
                    "score": self._prepare_score_for_payload(player.score),
                    "answered": player.answered,
                    "response_time": player.last_response_time,
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
        payload["server_time"] = self._current_time_iso()
        return payload

    def _build_scoreboard(self, room: Room) -> List[Dict[str, str | int | float | None]]:
        scoreboard: List[Dict[str, str | int | float | None]] = []
        for player in room.players.values():
            answered_count = len(player.response_times)
            total_response_time = player.total_response_time if answered_count else 0.0
            average_response_time: float | None = (
                total_response_time / answered_count if answered_count else None
            )
            scoreboard.append(
                {
                    "player": player.name,
                    "score": self._prepare_score_for_payload(player.score),
                    "answered_count": answered_count,
                    "total_response_time": total_response_time,
                    "average_response_time": average_response_time,
                }
            )

        def sort_key(item: Dict[str, str | int | float | None]) -> tuple:
            score_value = self._coerce_score_value(item.get("score"), default=0.0)
            answered = int(item.get("answered_count", 0))
            average = item.get("average_response_time")
            average_value = float("inf")
            if isinstance(average, (int, float)):
                average_value = float(average)
            return (-score_value, -answered, average_value, str(item["player"]))

        scoreboard.sort(key=sort_key)
        return scoreboard

    async def _handle_question_timeout(self, room: Room, duration: int) -> None:
        try:
            await asyncio.sleep(duration)
            # Если вопрос уже сменился — ничего не делаем.
            if room.question_timeout_task is not asyncio.current_task():
                return

            for player in room.players.values():
                self._ensure_player_tracking(player)
                if not player.answered:
                    room.answers.setdefault(player.name, None)
                    player.answered = True
                    player.last_response_time = None

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

    @staticmethod
    def _ensure_player_tracking(player: Player) -> None:
        if not hasattr(player, "last_answered_at"):
            player.last_answered_at = None
        if not hasattr(player, "last_response_time"):
            player.last_response_time = None
        if not hasattr(player, "response_times") or player.response_times is None:
            player.response_times = []
        if not hasattr(player, "total_response_time") or player.total_response_time is None:
            player.total_response_time = 0.0
        if not hasattr(player, "min_response_time"):
            player.min_response_time = None
        if not hasattr(player, "max_response_time"):
            player.max_response_time = None

    @staticmethod
    def _coerce_score_value(value: Any, *, default: float | None = 0.0) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return default
            normalized = stripped.replace(",", ".")
            try:
                return float(Decimal(normalized))
            except (InvalidOperation, ValueError):
                return default
        if value is None:
            return default
        return default

    def _extract_question_score(self, question: Dict[str, Any]) -> float:
        raw_score = question.get("score")
        score = self._coerce_score_value(raw_score, default=None)
        if score is None:
            return 1.0
        return score

    @staticmethod
    def _normalize_score(value: float, *, places: int = 4) -> float:
        try:
            decimal_value = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return float(value)
        quant = Decimal("1").scaleb(-places)
        normalized = decimal_value.quantize(quant, rounding=ROUND_HALF_UP).normalize()
        return float(normalized)

    @staticmethod
    def _prepare_score_for_payload(value: float) -> float | int:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return value  # type: ignore[return-value]
        if abs(numeric - round(numeric)) < 1e-9:
            return int(round(numeric))
        return numeric

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
