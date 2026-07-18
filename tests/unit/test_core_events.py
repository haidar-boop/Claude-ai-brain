"""Tests for aiforge.core.events."""

from __future__ import annotations

import pytest

from aiforge.core.events import Event, EventBus


def test_publish_invokes_subscribed_handler() -> None:
    bus = EventBus()
    received: list[Event] = []
    bus.subscribe("greeting", received.append)
    bus.publish(Event(name="greeting", payload={"who": "world"}))
    assert len(received) == 1
    assert received[0].payload == {"who": "world"}


def test_publish_ignores_unrelated_event_names() -> None:
    bus = EventBus()
    received: list[Event] = []
    bus.subscribe("a", received.append)
    bus.publish(Event(name="b"))
    assert received == []


def test_multiple_handlers_run_in_subscription_order() -> None:
    bus = EventBus()
    order: list[str] = []
    bus.subscribe("x", lambda e: order.append("first"))
    bus.subscribe("x", lambda e: order.append("second"))
    bus.publish(Event(name="x"))
    assert order == ["first", "second"]


def test_unsubscribe_stops_future_delivery() -> None:
    bus = EventBus()
    received: list[Event] = []
    unsubscribe = bus.subscribe("x", received.append)
    bus.publish(Event(name="x"))
    unsubscribe()
    bus.publish(Event(name="x"))
    assert len(received) == 1


def test_handler_exception_propagates() -> None:
    bus = EventBus()

    def boom(event: Event) -> None:
        raise ValueError("boom")

    bus.subscribe("x", boom)
    with pytest.raises(ValueError, match="boom"):
        bus.publish(Event(name="x"))


def test_emit_convenience_builds_event() -> None:
    bus = EventBus()
    received: list[Event] = []
    bus.subscribe("greeting", received.append)
    bus.emit("greeting", who="world")
    assert received[0].payload == {"who": "world"}


def test_event_defaults_to_empty_payload() -> None:
    event = Event(name="noop")
    assert event.payload == {}
