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


class FrozenDateTime:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def now(self, tz=None):
        value = self.current
        if tz is None:
            return value.replace(tzinfo=None)
        return value.astimezone(tz)


class DummyTask:
    def __init__(self, coro=None) -> None:
        self._coro = coro
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True
        if self._coro is not None:
            try:
                self._coro.close()
            except RuntimeError:
                # The coroutine might be already closed or running; ignore in tests.
                pass


def _patch_datetime(monkeypatch, current: datetime) -> datetime:
    frozen = FrozenDateTime(current)
    monkeypatch.setattr(
        manager_module,
        "datetime",
        types.SimpleNamespace(now=frozen.now),
    )
    return current.astimezone(timezone.utc)


def test_schedule_auto_start_records_state_and_events(monkeypatch):
    async def scenario() -> None:
        manager = ScreenRoomManager()
        room = manager.create_room("room-auto", quiz_id=7)

        server_time = "2024-01-01T12:00:00+00:00"
        monkeypatch.setattr(manager, "_current_time_iso", lambda: server_time)

        now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        _patch_datetime(monkeypatch, now)

        start_at = now + timedelta(seconds=42)

        dummy_task = DummyTask()

        def fake_create_task(coro):
            dummy_task._coro = coro
            return dummy_task

        monkeypatch.setattr(manager_module.asyncio, "create_task", fake_create_task)

        await manager.schedule_auto_start(room.room_id, start_at, origin="ui")

        assert room.auto_start_task is dummy_task
        assert room.auto_start_origin == "ui"
        assert room.auto_start_at == start_at

        assert room.events
        event_name, payload = room.events[-1]
        assert event_name == "auto_start_scheduled"
        assert payload["scheduled_at"] == start_at.isoformat()
        assert payload["origin"] == "ui"
        assert payload["server_time"] == server_time
        assert payload["delay"] == pytest.approx(42.0)

        dummy_task.cancel()

    asyncio.run(scenario())


def test_cancel_auto_start_cancels_task_and_notifies(monkeypatch):
    async def scenario() -> None:
        manager = ScreenRoomManager()
        room = manager.create_room("room-cancel", quiz_id=11)

        server_time = "2024-02-02T00:00:00+00:00"
        monkeypatch.setattr(manager, "_current_time_iso", lambda: server_time)

        now = datetime(2024, 2, 2, 0, 0, 0, tzinfo=timezone.utc)
        _patch_datetime(monkeypatch, now)

        start_at = now + timedelta(seconds=30)

        dummy_task = DummyTask()

        def fake_create_task(coro):
            dummy_task._coro = coro
            return dummy_task

        monkeypatch.setattr(manager_module.asyncio, "create_task", fake_create_task)

        await manager.schedule_auto_start(room.room_id, start_at, origin="auto")

        room.events.clear()

        await manager.cancel_auto_start(
            room.room_id, origin="manual", reason="changed_mind"
        )

        assert dummy_task.cancelled is True
        assert room.auto_start_task is None
        assert room.auto_start_at is None
        assert room.auto_start_origin is None

        assert room.events
        event_name, payload = room.events[-1]
        assert event_name == "auto_start_cancelled"
        assert payload["origin"] == "manual"
        assert payload["reason"] == "changed_mind"
        assert payload["server_time"] == server_time
        assert payload["scheduled_at"] == start_at.isoformat()

    asyncio.run(scenario())


def test_auto_start_runs_game_and_clears_state(monkeypatch):
    async def scenario() -> None:
        manager = ScreenRoomManager()
        room = manager.create_room("room-run", quiz_id=21)

        server_time = "2024-03-03T09:30:00+00:00"
        monkeypatch.setattr(manager, "_current_time_iso", lambda: server_time)

        now = datetime(2024, 3, 3, 9, 30, 0, tzinfo=timezone.utc)
        _patch_datetime(monkeypatch, now)

        room.questions = [
            {
                "id": 1,
                "text": "Sample question",
                "timer": 15,
                "options": ["A", "B", "C"],
            }
        ]

        existing_timer = DummyTask()
        room.question_timeout_task = existing_timer
        room.events.append(("previous_event", {}))

        send_json_mock = AsyncMock()
        monkeypatch.setattr(manager, "_send_json", send_json_mock)

        original_create_task = manager_module.asyncio.create_task

        def fake_create_task(coro):
            name = getattr(getattr(coro, "cr_code", None), "co_name", "")
            if name == "_handle_question_timeout":
                return DummyTask(coro)
            return original_create_task(coro)

        monkeypatch.setattr(manager_module.asyncio, "create_task", fake_create_task)

        await manager.schedule_auto_start(room.room_id, now, origin="scheduler")

        await asyncio.sleep(0)

        assert existing_timer.cancelled is True
        assert room.auto_start_task is None
        assert room.auto_start_at is None
        assert room.auto_start_origin is None

        assert room.current_question_index == 0
        assert room.question_duration == 15
        assert room.question_started_at is not None

        assert len(room.events) == 1
        event_name, payload = room.events[0]
        assert event_name == "show_question"
        assert payload["question_number"] == 1
        assert payload["total_questions"] == 1
        assert payload["server_time"] == server_time

        for call in send_json_mock.await_args_list:
            assert call.args[1] != "error"

        if isinstance(room.question_timeout_task, DummyTask):
            room.question_timeout_task.cancel()

    asyncio.run(scenario())
