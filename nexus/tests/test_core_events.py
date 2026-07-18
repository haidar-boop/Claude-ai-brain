"""Tests for nexus.core.events."""

from __future__ import annotations

from nexus.core.events import Event, EventBus


def test_subscribe_and_publish() -> None:
    bus = EventBus()
    seen: list[Event] = []
    bus.subscribe("note.created", seen.append)
    bus.publish("note.created", note_id=1, title="Hi")
    assert len(seen) == 1
    assert seen[0].name == "note.created"
    assert seen[0].payload == {"note_id": 1, "title": "Hi"}


def test_wildcard_receives_everything() -> None:
    bus = EventBus()
    seen: list[str] = []
    bus.subscribe("*", lambda e: seen.append(e.name))
    bus.publish("a.one")
    bus.publish("b.two")
    assert seen == ["a.one", "b.two"]


def test_unsubscribe_stops_delivery() -> None:
    bus = EventBus()
    seen: list[Event] = []
    unsubscribe = bus.subscribe("x", seen.append)
    bus.publish("x")
    unsubscribe()
    bus.publish("x")
    assert len(seen) == 1


def test_handler_exception_does_not_break_others() -> None:
    bus = EventBus()
    delivered: list[str] = []

    def boom(_: Event) -> None:
        raise RuntimeError("handler bug")

    bus.subscribe("t", boom)
    bus.subscribe("t", lambda e: delivered.append(e.name))
    bus.publish("t")
    assert delivered == ["t"]  # second handler still ran


def test_clear_removes_all() -> None:
    bus = EventBus()
    seen: list[Event] = []
    bus.subscribe("x", seen.append)
    bus.subscribe("*", seen.append)
    bus.clear()
    bus.publish("x")
    assert seen == []
