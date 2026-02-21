"""Lightweight pub/sub event bus for decoupling components.

Allows mixins to emit events without knowing who handles them.
Subscribers register callbacks; the bus dispatches with error isolation.
"""
from __future__ import annotations
from enum import Enum, auto
from typing import Any, Callable, Dict, List

from app.logging_utils import get_logger

_log = get_logger("events")


class AppEvent(Enum):
    """Application-wide events for inter-component communication."""
    GAMES_CHANGED = auto()       # after add/edit/delete/import/scan
    GAME_EDITED = auto()         # single game metadata changed (data: game_id)
    LIBRARY_LOADED = auto()      # after initial load or reload
    COLLECTION_CHANGED = auto()  # after collection CRUD
    SCAN_COMPLETE = auto()       # after scan finishes (data: scan_result)
    FILTER_CHANGED = auto()      # after filter/search change
    THEME_CHANGED = auto()       # after theme switch


class EventBus:
    """Lightweight pub/sub event bus for decoupling components."""

    def __init__(self) -> None:
        self._subs: Dict[AppEvent, List[Callable]] = {}

    def on(self, event: AppEvent, callback: Callable) -> None:
        """Subscribe to an event."""
        self._subs.setdefault(event, []).append(callback)

    def off(self, event: AppEvent, callback: Callable) -> None:
        """Unsubscribe from an event."""
        if event in self._subs:
            self._subs[event] = [cb for cb in self._subs[event] if cb is not callback]

    def emit(self, event: AppEvent, data: Any = None) -> None:
        """Emit an event, calling all registered callbacks."""
        for cb in self._subs.get(event, []):
            try:
                cb(data)
            except Exception:
                _log.exception("event_handler_error event=%s", event.name)
