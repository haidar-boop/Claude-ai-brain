"""Tests for nexus.services.automation."""

from __future__ import annotations

import pytest

from nexus.automation.rules import ActionRegistry, ActionSpec, Condition, RuleEngine
from nexus.core.errors import NotFoundError, ValidationError
from nexus.core.events import EventBus
from nexus.db.database import Database
from nexus.services.automation import AutomationService


@pytest.fixture
def service() -> AutomationService:
    return AutomationService(Database.in_memory(), EventBus())


def test_create_and_get_rule(service: AutomationService) -> None:
    dto = service.create_rule(
        "pdf-inbox",
        "fs.created",
        conditions=[Condition("path", "endswith", ".pdf")],
        actions=[ActionSpec("index_file", {"move_to": "Documents"})],
    )
    fetched = service.get_rule(dto.id)
    assert fetched.name == "pdf-inbox"
    assert fetched.trigger == "fs.created"
    assert fetched.conditions[0].op == "endswith"
    assert fetched.actions[0].type == "index_file"
    assert fetched.actions[0].params == {"move_to": "Documents"}


def test_conditions_and_actions_round_trip_through_json(service: AutomationService) -> None:
    service.create_rule(
        "r",
        "topic",
        conditions=[Condition("a", "eq", 1), Condition("b", "gt", 2)],
        actions=[ActionSpec("x"), ActionSpec("y", {"k": "v"})],
    )
    dto = service.list_rules()[0]
    assert len(dto.conditions) == 2
    assert len(dto.actions) == 2
    assert dto.actions[1].params == {"k": "v"}


def test_blank_name_rejected(service: AutomationService) -> None:
    with pytest.raises(ValidationError):
        service.create_rule("  ", "topic")


def test_blank_trigger_rejected(service: AutomationService) -> None:
    with pytest.raises(ValidationError):
        service.create_rule("r", "  ")


def test_duplicate_name_rejected(service: AutomationService) -> None:
    service.create_rule("dup", "topic")
    with pytest.raises(ValidationError, match="already exists"):
        service.create_rule("dup", "other")


def test_set_enabled_and_filter(service: AutomationService) -> None:
    a = service.create_rule("a", "t")
    service.create_rule("b", "t", enabled=False)
    assert {r.name for r in service.list_rules(enabled_only=True)} == {"a"}
    service.set_enabled(a.id, False)
    assert service.list_rules(enabled_only=True) == []


def test_delete_rule(service: AutomationService) -> None:
    dto = service.create_rule("gone", "t")
    service.delete_rule(dto.id)
    with pytest.raises(NotFoundError):
        service.get_rule(dto.id)


def test_load_into_engine_only_enabled(service: AutomationService) -> None:
    bus = EventBus()
    registry = ActionRegistry()
    calls: list[str] = []
    registry.register("count", lambda event, params: calls.append(event.name))
    engine = RuleEngine(bus, registry)

    service.create_rule("on", "topic", actions=[ActionSpec("count")], enabled=True)
    service.create_rule("off", "topic", actions=[ActionSpec("count")], enabled=False)
    loaded = service.load_into(engine)
    assert loaded == 1

    bus.publish("topic")
    assert calls == ["topic"]  # only the enabled rule ran


def test_load_into_is_idempotent(service: AutomationService) -> None:
    bus = EventBus()
    registry = ActionRegistry()
    calls: list[int] = []
    registry.register("count", lambda event, params: calls.append(1))
    engine = RuleEngine(bus, registry)
    service.create_rule("r", "topic", actions=[ActionSpec("count")])
    service.load_into(engine)
    service.load_into(engine)  # reloading must not double-fire
    bus.publish("topic")
    assert calls == [1]


def test_events_published(service: AutomationService) -> None:
    seen: list[str] = []
    service._events.subscribe("*", lambda e: seen.append(e.name))
    dto = service.create_rule("r", "t")
    service.set_enabled(dto.id, False)
    service.delete_rule(dto.id)
    assert seen == [
        "automation.rule_created",
        "automation.rule_toggled",
        "automation.rule_deleted",
    ]
