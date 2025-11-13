import asyncio
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from screen import manager as manager_module
from screen.manager import ScreenRoomManager


class FakeClock:
    def __init__(self, start: datetime) -> None:
        self.current = start

    def now(self, tz=None):
        value = self.current
        if tz is None:
            return value.replace(tzinfo=None)
        return value.astimezone(tz)

    def set(self, value: datetime) -> None:
        self.current = value

    def advance(self, seconds: float) -> None:
        self.current = self.current + timedelta(seconds=seconds)


def prepare_question(room, clock: FakeClock, *, index: int, duration: int) -> None:
    room.current_question_index = index
    room.question_duration = duration
    room.question_started_at = clock.current
    room.answers.clear()
    for player in room.players.values():
        player.answered = False
        player.last_answered_at = None
        player.last_response_time = None


def test_response_time_tracking_for_multiple_players(monkeypatch):
    manager = ScreenRoomManager()
    room_id = "room-1"
    manager.create_room(room_id)
    players = ("Alice", "Bob")
    for player_name in players:
        manager.add_player(room_id, player_name)

    clock = FakeClock(datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc))

    monkeypatch.setattr(
        manager_module,
        "datetime",
        types.SimpleNamespace(now=clock.now),
    )

    room = manager.get_room(room_id)
    assert room is not None

    room.questions = [
        {"id": 1, "timer": 30},
        {"id": 2, "timer": 25},
        {"id": 3, "timer": 20},
    ]

    # Answers before the first question starts must be ignored entirely.
    asyncio.run(manager.submit_answer(room_id, "Alice", "A"))
    assert "Alice" not in room.answers
    alice = room.players["Alice"]
    assert alice.response_times == []
    assert alice.total_response_time == pytest.approx(0)

    expected_sequences = {name: [] for name in players}

    question_durations = [18, 22, 26]
    per_question_times = [
        {"Alice": 1.25, "Bob": 2.5},
        {"Alice": 4.75, "Bob": 3.5},
        {"Alice": 2.0, "Bob": 5.25},
    ]

    for index, per_player in enumerate(per_question_times):
        prepare_question(room, clock, index=index, duration=question_durations[index])
        start_time = clock.current
        for player_name, duration in per_player.items():
            clock.set(start_time + timedelta(seconds=duration))
            asyncio.run(manager.submit_answer(room_id, player_name, "A"))
            expected_sequences[player_name].append(min(duration, question_durations[index]))
            if index == 0 and player_name == "Alice":
                previous_times = list(expected_sequences[player_name])
                clock.set(start_time + timedelta(seconds=duration + 3))
                asyncio.run(manager.submit_answer(room_id, player_name, "A"))
                player = room.players[player_name]
                assert player.response_times == pytest.approx(
                    previous_times, rel=0, abs=1e-9
                )
        # Advance clock slightly before the next question would start.
        max_duration = max(per_player.values())
        question_end = max(
            clock.current, start_time + timedelta(seconds=max_duration)
        )
        clock.set(question_end + timedelta(seconds=1))

    for player_name in players:
        player = room.players[player_name]
        assert player.response_times == pytest.approx(
            expected_sequences[player_name], rel=0, abs=1e-9
        )
        assert player.total_response_time == pytest.approx(
            sum(expected_sequences[player_name]), rel=0, abs=1e-9
        )

    scoreboard = manager._build_scoreboard(room)
    scoreboard_by_player = {entry["player"]: entry for entry in scoreboard}
    assert set(scoreboard_by_player.keys()) == set(players)
    for player_name in players:
        entry = scoreboard_by_player[player_name]
        expected = expected_sequences[player_name]
        assert entry["answered_count"] == len(expected)
        assert entry["total_response_time"] == pytest.approx(
            sum(expected), rel=0, abs=1e-9
        )
        assert entry["average_response_time"] == pytest.approx(
            sum(expected) / len(expected), rel=0, abs=1e-9
        )


def test_answers_after_timeout_are_ignored(monkeypatch):
    manager = ScreenRoomManager()
    room_id = "room-timeout"
    manager.create_room(room_id)
    for name in ("Alice", "Bob"):
        manager.add_player(room_id, name)

    start = datetime(2024, 6, 1, 18, 0, 0, tzinfo=timezone.utc)
    clock = FakeClock(start)
    monkeypatch.setattr(
        manager_module,
        "datetime",
        types.SimpleNamespace(now=clock.now),
    )

    room = manager.get_room(room_id)
    assert room is not None

    room.questions = [{"id": 1, "timer": 5}]
    prepare_question(room, clock, index=0, duration=5)

    broadcast_mock = AsyncMock()
    monkeypatch.setattr(manager, "broadcast", broadcast_mock)
    next_question_mock = AsyncMock()
    monkeypatch.setattr(manager, "show_next_question", next_question_mock)

    async def immediate_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(manager_module.asyncio, "sleep", immediate_sleep)

    async def scenario() -> None:
        # Alice answers, but the server clamps the recorded value to the question duration.
        clock.set(start + timedelta(seconds=9))
        await manager.submit_answer(room_id, "Alice", "A")

        async def trigger_timeout():
            room.question_timeout_task = asyncio.current_task()
            await manager._handle_question_timeout(room, room.question_duration)

        await trigger_timeout()

        # Bob's late answer after the timeout must be ignored completely.
        clock.set(start + timedelta(seconds=12))
        await manager.submit_answer(room_id, "Bob", "B")

    asyncio.run(scenario())

    alice = room.players["Alice"]
    assert alice.response_times == pytest.approx([5.0], rel=0, abs=1e-9)
    assert alice.total_response_time == pytest.approx(5.0, rel=0, abs=1e-9)

    bob = room.players["Bob"]
    assert bob.response_times == []
    assert bob.total_response_time == pytest.approx(0)
    assert room.answers.get("Bob") is None

    scoreboard = manager._build_scoreboard(room)
    scoreboard_by_player = {entry["player"]: entry for entry in scoreboard}
    assert scoreboard_by_player["Alice"]["total_response_time"] == pytest.approx(
        5.0, rel=0, abs=1e-9
    )
    assert scoreboard_by_player["Bob"]["total_response_time"] == pytest.approx(
        0.0, rel=0, abs=1e-9
    )

