"""Tests for events.py — EventBus pub/sub system."""
import pytest
from app.events import EventBus, AppEvent


class TestEventBus:
    def test_emit_calls_subscriber(self):
        bus = EventBus()
        received = []
        bus.on(AppEvent.GAMES_CHANGED, lambda data: received.append(data))
        bus.emit(AppEvent.GAMES_CHANGED, "test_data")
        assert received == ["test_data"]

    def test_multiple_subscribers(self):
        bus = EventBus()
        calls = []
        bus.on(AppEvent.GAMES_CHANGED, lambda d: calls.append("a"))
        bus.on(AppEvent.GAMES_CHANGED, lambda d: calls.append("b"))
        bus.emit(AppEvent.GAMES_CHANGED)
        assert calls == ["a", "b"]

    def test_emit_without_subscribers(self):
        bus = EventBus()
        # Should not raise
        bus.emit(AppEvent.GAMES_CHANGED, "data")

    def test_off_removes_subscriber(self):
        bus = EventBus()
        calls = []
        cb = lambda d: calls.append("called")
        bus.on(AppEvent.GAMES_CHANGED, cb)
        bus.off(AppEvent.GAMES_CHANGED, cb)
        bus.emit(AppEvent.GAMES_CHANGED)
        assert calls == []

    def test_different_events_isolated(self):
        bus = EventBus()
        calls = []
        bus.on(AppEvent.GAMES_CHANGED, lambda d: calls.append("games"))
        bus.on(AppEvent.THEME_CHANGED, lambda d: calls.append("theme"))
        bus.emit(AppEvent.GAMES_CHANGED)
        assert calls == ["games"]

    def test_subscriber_error_does_not_break_others(self):
        bus = EventBus()
        calls = []

        def bad_handler(data):
            raise ValueError("oops")

        bus.on(AppEvent.GAMES_CHANGED, bad_handler)
        bus.on(AppEvent.GAMES_CHANGED, lambda d: calls.append("ok"))
        bus.emit(AppEvent.GAMES_CHANGED)
        assert calls == ["ok"]

    def test_emit_with_none_data(self):
        bus = EventBus()
        received = []
        bus.on(AppEvent.GAME_EDITED, lambda d: received.append(d))
        bus.emit(AppEvent.GAME_EDITED)
        assert received == [None]
