"""A minimal synchronous event bus for cross-cutting observability.

Used by the engine to publish lifecycle events (request started, provider
selected, skills resolved, response received) that logging, metrics, or a UI
layer can subscribe to without the engine knowing anything about those
consumers.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

__all__ = ["Event", "EventBus", "Handler"]

Handler = Callable[["Event"], None]


@dataclass(frozen=True, slots=True)
class Event:
    """A single event published on the bus."""

    name: str
    payload: dict[str, Any] = field(default_factory=dict)


class EventBus:
    """Synchronous, in-process publish/subscribe event bus."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, name: str, handler: Handler) -> Callable[[], None]:
        """Register *handler* for events named *name*.

        Returns an idempotent unsubscribe callable.
        """
        self._handlers[name].append(handler)

        def unsubscribe() -> None:
            handlers = self._handlers.get(name)
            if handlers and handler in handlers:
                handlers.remove(handler)

        return unsubscribe

    def publish(self, event: Event) -> None:
        """Synchronously invoke every handler subscribed to *event.name*.

        Handlers run in subscription order. If a handler raises, the
        exception propagates immediately and any remaining handlers for this
        event do not run.
        """
        for handler in list(self._handlers.get(event.name, ())):
            handler(event)

    def emit(self, name: str, **payload: Any) -> None:
        """Build and publish an :class:`Event` from *name* and *payload* in one call."""
        self.publish(Event(name=name, payload=payload))
