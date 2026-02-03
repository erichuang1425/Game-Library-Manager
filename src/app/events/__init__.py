"""
Event bus system for decoupled communication.

Provides a publish/subscribe pattern for loose coupling between
application components.

Usage:
    from app.events import Event, get_event_bus

    # Subscribe to an event
    def on_game_added(game):
        print(f"Game added: {game.title}")

    bus = get_event_bus()
    bus.subscribe(Event.GAME_ADDED, on_game_added)

    # Emit an event
    bus.emit(Event.GAME_ADDED, game)
"""

from .event_bus import (
    Event,
    EventBus,
    EventPriority,
    get_event_bus,
    emit,
    subscribe,
    unsubscribe,
)

__all__ = [
    "Event",
    "EventBus",
    "EventPriority",
    "get_event_bus",
    "emit",
    "subscribe",
    "unsubscribe",
]
