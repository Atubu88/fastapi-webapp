from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class Room:
    """Простая структура данных для хранения информации о комнате."""

    room_id: str
    players: Dict[str, "Player"] = field(default_factory=dict)
    metadata: Dict[str, str] = field(default_factory=dict)
    events: list[tuple[str, dict | None]] = field(default_factory=list)


@dataclass
class Player:
    """Игрок, подключённый к комнате."""

    name: str
    answered: bool = False


class ScreenRoomManager:
    """In-memory менеджер комнат экранного режима."""

    def __init__(self) -> None:
        self._rooms: Dict[str, Room] = {}

    def create_room(self, room_id: str) -> Room:
        room = Room(room_id=room_id)
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
        return player

    def all_answered(self, room_id: str) -> bool:
        room = self.get_room(room_id)
        if room is None or not room.players:
            return False
        return all(player.answered for player in room.players.values())

    def broadcast(self, room_id: str, event: str, payload: Dict | None = None) -> None:
        room = self.get_room(room_id)
        if room is None:
            raise ValueError(f"Room '{room_id}' not found")
        room.events.append((event, payload))


room_manager = ScreenRoomManager()
