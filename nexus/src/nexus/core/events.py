"""A small, thread-safe in-process event bus.

Services publish domain events (``note.created``, ``task.completed``, ...)
without knowing who consumes them; the UI, the dashboard's activity feed,
and the automation rule engine subscribe to what they care about. This
keeps modules decoupled -- a service never imports a panel, it just emits.

Handlers run synchronously on the publishing thread. A misbehaving handler
is logged and skipped rather than being allowed to abort the publish and
take out unrelated subscribers, because an event is a notification, not a
transaction: one broken listener must not stop the others from hearing it.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from nexus.core.logging import get_logger

__all__ = ["Event", "EventBus"]

_logger = get_logger("events")

Handler = Callable[["Event"], None]


@dataclass(frozen=True, slots=True)
class Event:
    """An immutable notification that something happened.

    *name* is a dotted topic (``"note.created"``); *payload* carries
    event-specific data (typically ids and a human-readable summary, not
    whole ORM objects, so subscribers stay loosely coupled).
    """

    name: str
    payload: dict[str, Any] = field(default_factory=dict)


class EventBus:
    """Subscribe/publish hub for :class:`Event` notifications."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = {}
        self._wildcard: list[Handler] = []
        self._lock = threading.RLock()

    def subscribe(self, name: str, handler: Handler) -> Callable[[], None]:
        """Register *handler* for events named *name* (or ``"*"`` for all).

        Returns an unsubscribe callable, so callers -- especially Qt panels
        with a limited lifetime -- can cleanly detach without needing a
        reference to the exact list they were added to.
        """
        with self._lock:
            bucket = self._wildcard if name == "*" else self._handlers.setdefault(name, [])
            bucket.append(handler)

        def unsubscribe() -> None:
            with self._lock:
                target = self._wildcard if name == "*" else self._handlers.get(name, [])
                if handler in target:
                    target.remove(handler)

        return unsubscribe

    def publish(self, topic: str, **payload: Any) -> Event:
        """Build and dispatch an :class:`Event`, returning what was published.

        The event name is the positional *topic* argument (not ``name``) so
        that ``name`` remains free as an ordinary payload key -- publishing
        ``bus.publish("project.created", name="Work")`` must not collide with
        the parameter that carries the topic.
        """
        event = Event(name=topic, payload=payload)
        with self._lock:
            targets = [*self._handlers.get(topic, ()), *self._wildcard]
        for handler in targets:
            try:
                handler(event)
            except Exception:
                _logger.exception("event handler failed for %s", topic)
        return event

    def clear(self) -> None:
        """Remove every subscription (used at shutdown and between tests)."""
        with self._lock:
            self._handlers.clear()
            self._wildcard.clear()
