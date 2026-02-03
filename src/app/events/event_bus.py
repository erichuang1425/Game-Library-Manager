"""
Central event bus for application-wide events.

Provides a publish/subscribe mechanism for loose coupling between
components without direct dependencies.
"""

import threading
import weakref
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from app.logging_utils import get_logger, kv

_log = get_logger("event_bus")


class Event(Enum):
    """
    Application-wide events.

    Events are organized by domain for clarity.
    """

    # Game events
    GAME_ADDED = auto()
    GAME_UPDATED = auto()
    GAME_DELETED = auto()
    GAME_LAUNCHED = auto()
    GAME_SELECTED = auto()

    # Library events
    LIBRARY_LOADED = auto()
    LIBRARY_SAVED = auto()
    LIBRARY_SCAN_STARTED = auto()
    LIBRARY_SCAN_COMPLETED = auto()

    # Collection events
    COLLECTION_CREATED = auto()
    COLLECTION_UPDATED = auto()
    COLLECTION_DELETED = auto()
    COLLECTION_GAME_ADDED = auto()
    COLLECTION_GAME_REMOVED = auto()

    # Download events
    DOWNLOAD_QUEUED = auto()
    DOWNLOAD_STARTED = auto()
    DOWNLOAD_PROGRESS = auto()
    DOWNLOAD_COMPLETED = auto()
    DOWNLOAD_FAILED = auto()
    DOWNLOAD_CANCELLED = auto()

    # Archive events
    ARCHIVE_EXTRACT_STARTED = auto()
    ARCHIVE_EXTRACT_PROGRESS = auto()
    ARCHIVE_EXTRACT_COMPLETED = auto()
    ARCHIVE_EXTRACT_FAILED = auto()

    # Update events
    UPDATES_CHECK_STARTED = auto()
    UPDATES_CHECK_PROGRESS = auto()
    UPDATES_CHECK_COMPLETED = auto()
    UPDATES_AVAILABLE = auto()

    # UI events
    THEME_CHANGED = auto()
    VIEW_MODE_CHANGED = auto()
    FILTER_CHANGED = auto()
    SETTINGS_CHANGED = auto()

    # Application events
    APP_STARTUP = auto()
    APP_SHUTDOWN = auto()
    APP_ERROR = auto()


class EventPriority(Enum):
    """Priority levels for event handlers."""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


# Type alias for event callbacks
EventCallback = Callable[[Any], None]


@dataclass
class Subscription:
    """Represents an event subscription."""
    callback: EventCallback
    priority: EventPriority = EventPriority.NORMAL
    once: bool = False
    weak: bool = False
    _weak_ref: Optional[weakref.ref] = field(default=None, repr=False)


class EventBus:
    """
    Central event bus for application-wide events.

    Thread-safe singleton implementation with support for:
    - Multiple subscribers per event
    - Priority ordering of handlers
    - One-time subscriptions
    - Weak references to avoid memory leaks
    - Event history for debugging
    """

    _instance: Optional["EventBus"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "EventBus":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialize()
            return cls._instance

    def _initialize(self) -> None:
        """Initialize the event bus."""
        self._subscribers: Dict[Event, List[Subscription]] = {}
        self._event_lock = threading.RLock()
        self._history: List[Tuple[Event, Any]] = []
        self._max_history = 100
        self._paused = False
        self._queued_events: List[Tuple[Event, Any]] = []

    def subscribe(
        self,
        event: Event,
        callback: EventCallback,
        priority: EventPriority = EventPriority.NORMAL,
        once: bool = False,
        weak: bool = False,
    ) -> Callable[[], None]:
        """
        Subscribe to an event.

        Args:
            event: The event to subscribe to
            callback: Function to call when event is emitted
            priority: Handler priority (higher runs first)
            once: If True, automatically unsubscribe after first call
            weak: If True, use weak reference (auto-cleanup when callback's
                  object is garbage collected)

        Returns:
            Unsubscribe function for convenience
        """
        with self._event_lock:
            if event not in self._subscribers:
                self._subscribers[event] = []

            sub = Subscription(
                callback=callback,
                priority=priority,
                once=once,
                weak=weak,
            )

            if weak:
                # Try to create weak reference
                try:
                    sub._weak_ref = weakref.ref(callback)
                except TypeError:
                    # Can't create weak ref to this type
                    sub.weak = False

            self._subscribers[event].append(sub)

            # Sort by priority (highest first)
            self._subscribers[event].sort(
                key=lambda s: s.priority.value,
                reverse=True
            )

            _log.debug("event_subscribed %s", kv(
                event=event.name,
                priority=priority.name,
                once=once
            ))

        return lambda: self.unsubscribe(event, callback)

    def unsubscribe(self, event: Event, callback: EventCallback) -> bool:
        """
        Unsubscribe from an event.

        Args:
            event: The event to unsubscribe from
            callback: The callback to remove

        Returns:
            True if subscription was found and removed
        """
        with self._event_lock:
            if event not in self._subscribers:
                return False

            original_len = len(self._subscribers[event])
            self._subscribers[event] = [
                s for s in self._subscribers[event]
                if s.callback != callback
            ]

            removed = len(self._subscribers[event]) < original_len
            if removed:
                _log.debug("event_unsubscribed %s", kv(event=event.name))

            return removed

    def emit(self, event: Event, data: Any = None) -> int:
        """
        Emit an event to all subscribers.

        Args:
            event: The event to emit
            data: Data to pass to subscribers

        Returns:
            Number of subscribers notified
        """
        with self._event_lock:
            if self._paused:
                self._queued_events.append((event, data))
                return 0

            # Add to history
            self._history.append((event, data))
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

            if event not in self._subscribers:
                return 0

            # Get subscribers, filtering out dead weak refs
            to_remove = []
            active_subs = []

            for sub in self._subscribers[event]:
                if sub.weak and sub._weak_ref is not None:
                    cb = sub._weak_ref()
                    if cb is None:
                        to_remove.append(sub)
                        continue
                active_subs.append(sub)

            # Remove dead subscriptions
            for sub in to_remove:
                self._subscribers[event].remove(sub)

            # Track one-time subscriptions to remove
            once_subs = []

        # Call handlers outside the lock to prevent deadlocks
        count = 0
        for sub in active_subs:
            try:
                if sub.weak and sub._weak_ref is not None:
                    callback = sub._weak_ref()
                    if callback is None:
                        continue
                else:
                    callback = sub.callback

                callback(data)
                count += 1

                if sub.once:
                    once_subs.append(sub)

            except Exception as e:
                _log.exception("event_handler_error %s", kv(
                    event=event.name,
                    error=str(e)
                ))

        # Remove one-time subscriptions
        with self._event_lock:
            for sub in once_subs:
                if sub in self._subscribers.get(event, []):
                    self._subscribers[event].remove(sub)

        if count > 0:
            _log.debug("event_emitted %s", kv(
                event=event.name,
                subscribers=count
            ))

        return count

    def pause(self) -> None:
        """Pause event emission. Events will be queued."""
        with self._event_lock:
            self._paused = True
            _log.debug("event_bus_paused")

    def resume(self) -> int:
        """
        Resume event emission and emit queued events.

        Returns:
            Number of queued events processed
        """
        with self._event_lock:
            self._paused = False
            queued = self._queued_events.copy()
            self._queued_events.clear()

        count = 0
        for event, data in queued:
            self.emit(event, data)
            count += 1

        _log.debug("event_bus_resumed %s", kv(queued_processed=count))
        return count

    def clear_subscribers(self, event: Optional[Event] = None) -> int:
        """
        Clear subscribers.

        Args:
            event: Specific event to clear, or None to clear all

        Returns:
            Number of subscriptions cleared
        """
        with self._event_lock:
            if event is not None:
                count = len(self._subscribers.get(event, []))
                self._subscribers[event] = []
            else:
                count = sum(len(subs) for subs in self._subscribers.values())
                self._subscribers.clear()

            _log.debug("event_subscribers_cleared %s", kv(
                event=event.name if event else "all",
                count=count
            ))
            return count

    def get_history(
        self,
        event: Optional[Event] = None,
        limit: int = 20
    ) -> List[Tuple[Event, Any]]:
        """
        Get recent event history.

        Args:
            event: Filter to specific event type
            limit: Maximum number of events to return

        Returns:
            List of (event, data) tuples
        """
        with self._event_lock:
            if event is not None:
                filtered = [(e, d) for e, d in self._history if e == event]
            else:
                filtered = self._history.copy()

            return filtered[-limit:]

    def subscriber_count(self, event: Event) -> int:
        """Get number of subscribers for an event."""
        with self._event_lock:
            return len(self._subscribers.get(event, []))

    @property
    def is_paused(self) -> bool:
        """Check if event bus is paused."""
        return self._paused


# Global instance access
_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Get the global event bus instance."""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


# Convenience functions for common operations
def emit(event: Event, data: Any = None) -> int:
    """Emit an event using the global event bus."""
    return get_event_bus().emit(event, data)


def subscribe(
    event: Event,
    callback: EventCallback,
    priority: EventPriority = EventPriority.NORMAL,
    once: bool = False,
) -> Callable[[], None]:
    """Subscribe to an event using the global event bus."""
    return get_event_bus().subscribe(event, callback, priority, once)


def unsubscribe(event: Event, callback: EventCallback) -> bool:
    """Unsubscribe from an event using the global event bus."""
    return get_event_bus().unsubscribe(event, callback)
