"""Tests for nexus.automation.rules and the folder watcher's handler."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from nexus.automation.rules import (
    ActionRegistry,
    ActionSpec,
    Condition,
    Rule,
    RuleEngine,
    evaluate_condition,
)
from nexus.automation.watcher import _BusEventHandler
from nexus.core.errors import AutomationError
from nexus.core.events import Event, EventBus

# -- conditions -----------------------------------------------------------


def test_condition_eq_ne() -> None:
    payload = {"status": "done"}
    assert evaluate_condition(Condition("status", "eq", "done"), payload)
    assert not evaluate_condition(Condition("status", "eq", "todo"), payload)
    assert evaluate_condition(Condition("status", "ne", "todo"), payload)


def test_condition_string_ops() -> None:
    payload = {"path": "/inbox/report.pdf"}
    assert evaluate_condition(Condition("path", "contains", ".pdf"), payload)
    assert evaluate_condition(Condition("path", "startswith", "/inbox"), payload)
    assert evaluate_condition(Condition("path", "endswith", ".pdf"), payload)


def test_condition_numeric_ops() -> None:
    payload = {"size": 100}
    assert evaluate_condition(Condition("size", "gt", 50), payload)
    assert not evaluate_condition(Condition("size", "lt", 50), payload)


def test_condition_exists() -> None:
    assert evaluate_condition(Condition("x", "exists", True), {"x": 1})
    assert evaluate_condition(Condition("x", "exists", False), {})
    assert not evaluate_condition(Condition("x", "exists", True), {})


def test_missing_field_is_false_not_error() -> None:
    assert not evaluate_condition(Condition("absent", "eq", "y"), {"present": 1})


def test_incompatible_comparison_is_false() -> None:
    # gt between a string and an int shouldn't raise, just fail to hold.
    assert not evaluate_condition(Condition("v", "gt", 5), {"v": "text"})


def test_unknown_op_raises() -> None:
    with pytest.raises(AutomationError):
        evaluate_condition(Condition("v", "bogus", 1), {"v": 1})


# -- action registry ------------------------------------------------------


def test_action_registry() -> None:
    reg = ActionRegistry()
    reg.register("noop", lambda event, params: None)
    assert reg.has("noop")
    assert reg.names() == ["noop"]
    with pytest.raises(AutomationError):
        reg.get("missing")


# -- rule engine ----------------------------------------------------------


def test_rule_fires_action_on_matching_event() -> None:
    bus = EventBus()
    registry = ActionRegistry()
    calls: list[dict] = []
    registry.register("record", lambda event, params: calls.append({**event.payload, **params}))
    engine = RuleEngine(bus, registry)
    engine.add_rule(
        Rule(
            name="pdf-inbox",
            trigger="file.indexed",
            conditions=(Condition("path", "endswith", ".pdf"),),
            actions=(ActionSpec("record", {"tag": "pdf"}),),
        )
    )
    bus.publish("file.indexed", path="/inbox/a.pdf", file_id=1)
    bus.publish("file.indexed", path="/inbox/b.txt", file_id=2)  # condition fails
    assert calls == [{"path": "/inbox/a.pdf", "file_id": 1, "tag": "pdf"}]


def test_disabled_rule_does_not_fire() -> None:
    bus = EventBus()
    registry = ActionRegistry()
    calls: list[int] = []
    registry.register("count", lambda event, params: calls.append(1))
    engine = RuleEngine(bus, registry)
    engine.add_rule(Rule("r", "topic", actions=(ActionSpec("count"),), enabled=False))
    bus.publish("topic")
    assert calls == []


def test_unknown_action_is_logged_not_fatal() -> None:
    bus = EventBus()
    registry = ActionRegistry()
    engine = RuleEngine(bus, registry)
    engine.add_rule(Rule("r", "topic", actions=(ActionSpec("nonexistent"),)))
    # Must not raise even though the action isn't registered.
    bus.publish("topic")


def test_failing_action_does_not_break_dispatch() -> None:
    bus = EventBus()
    registry = ActionRegistry()
    ran: list[str] = []

    def boom(event: Event, params: dict) -> None:
        raise RuntimeError("action bug")

    registry.register("boom", boom)
    registry.register("ok", lambda event, params: ran.append("ok"))
    engine = RuleEngine(bus, registry)
    engine.add_rule(Rule("r", "topic", actions=(ActionSpec("boom"), ActionSpec("ok"))))
    bus.publish("topic")
    assert ran == ["ok"]  # second action still ran


def test_clear_unsubscribes() -> None:
    bus = EventBus()
    registry = ActionRegistry()
    calls: list[int] = []
    registry.register("count", lambda event, params: calls.append(1))
    engine = RuleEngine(bus, registry)
    engine.add_rule(Rule("r", "topic", actions=(ActionSpec("count"),)))
    engine.clear()
    bus.publish("topic")
    assert calls == []


# -- folder watcher handler ----------------------------------------------


def test_watcher_handler_publishes_bus_event() -> None:
    bus = EventBus()
    seen: list[Event] = []
    bus.subscribe("fs.created", seen.append)
    handler = _BusEventHandler(bus)
    handler.dispatch(
        SimpleNamespace(event_type="created", is_directory=False, src_path="/inbox/new.txt")
    )
    assert len(seen) == 1
    assert seen[0].payload["path"] == "/inbox/new.txt"


def test_watcher_handler_ignores_directories() -> None:
    bus = EventBus()
    seen: list[Event] = []
    bus.subscribe("*", seen.append)
    handler = _BusEventHandler(bus)
    handler.dispatch(SimpleNamespace(event_type="created", is_directory=True, src_path="/inbox/d"))
    assert seen == []


def test_watcher_handler_includes_dest_for_moves() -> None:
    bus = EventBus()
    seen: list[Event] = []
    bus.subscribe("fs.moved", seen.append)
    handler = _BusEventHandler(bus)
    handler.dispatch(
        SimpleNamespace(
            event_type="moved", is_directory=False, src_path="/a.txt", dest_path="/b.txt"
        )
    )
    assert seen[0].payload == {"path": "/a.txt", "dest_path": "/b.txt"}
