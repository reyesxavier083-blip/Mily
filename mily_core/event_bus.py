"""Small synchronous event bus for communication between MILY modules.

This bus is in-process only. It does not execute tools, persist events, or grant
permissions. Handler failures are returned to the publisher and do not prevent
other subscribed handlers from receiving the event.
"""

from collections.abc import Callable
from threading import RLock
from typing import Any

EventHandler = Callable[[str, Any], None]


class EventBus:
    """Publish named events to a snapshot of registered handlers."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._handlers: dict[str, list[EventHandler]] = {}

    def subscribe(self, event_name: str, handler: EventHandler) -> Callable[[], None]:
        """Subscribe to an event and return an idempotent unsubscribe function."""
        if not isinstance(event_name, str) or not event_name.strip():
            raise ValueError("event_name must be a non-empty string")
        if not callable(handler):
            raise TypeError("handler must be callable")

        with self._lock:
            self._handlers.setdefault(event_name, []).append(handler)

        subscribed = True

        def unsubscribe() -> None:
            nonlocal subscribed
            with self._lock:
                if not subscribed:
                    return
                subscribed = False
                handlers = self._handlers.get(event_name, [])
                try:
                    handlers.remove(handler)
                except ValueError:
                    pass
                if not handlers:
                    self._handlers.pop(event_name, None)

        return unsubscribe

    def publish(self, event_name: str, payload: Any = None) -> tuple[Exception, ...]:
        """Dispatch to current subscribers and return any handler exceptions."""
        if not isinstance(event_name, str) or not event_name.strip():
            raise ValueError("event_name must be a non-empty string")

        with self._lock:
            handlers = tuple(self._handlers.get(event_name, ()))

        errors: list[Exception] = []
        for handler in handlers:
            try:
                handler(event_name, payload)
            except Exception as exc:
                errors.append(exc)
        return tuple(errors)

    def subscriber_count(self, event_name: str) -> int:
        """Return the number of handlers currently subscribed to an event."""
        with self._lock:
            return len(self._handlers.get(event_name, ()))
