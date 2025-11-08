from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class Room:
    """Простая структура данных для хранения информации о комнате."""

    room_id: str
    metadata: Dict[str, str] = field(default_factory=dict)


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


room_manager = ScreenRoomManager()
