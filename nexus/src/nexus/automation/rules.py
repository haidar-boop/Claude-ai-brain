"""The rule engine: run configured actions when an event matches a rule.

A *rule* is the runtime of the "workflow builder": a trigger (an event topic
like ``file.indexed``), a list of conditions on the event payload, and a list
of actions to run when the trigger fires and every condition holds. Rules,
conditions, and actions are plain JSON-friendly data so they can be stored in
the database and edited by a UI, then loaded into a :class:`RuleEngine` that
subscribes to the event bus.

Actions are looked up by name in an :class:`ActionRegistry`, so the set of
things a rule can *do* is extensible without touching the engine: register a
new named action (send a notification, move a file, run a workflow) and rules
can use it immediately.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from nexus.core.errors import AutomationError
from nexus.core.events import Event, EventBus
from nexus.core.logging import get_logger

__all__ = [
    "ActionRegistry",
    "ActionSpec",
    "Condition",
    "Rule",
    "RuleEngine",
    "evaluate_condition",
]

_logger = get_logger("automation.rules")

# An action receives the triggering event and the action's static params.
ActionFn = Callable[[Event, dict[str, Any]], None]


@dataclass(frozen=True, slots=True)
class Condition:
    """A single test against a field of the event payload."""

    field: str
    op: str
    value: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {"field": self.field, "op": self.op, "value": self.value}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Condition:
        return cls(field=data["field"], op=data["op"], value=data.get("value"))


@dataclass(frozen=True, slots=True)
class ActionSpec:
    """A named action to run, plus static parameters for it."""

    type: str
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "params": self.params}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ActionSpec:
        return cls(type=data["type"], params=data.get("params", {}))


@dataclass(frozen=True, slots=True)
class Rule:
    """A trigger, its conditions, and the actions to run when they hold."""

    name: str
    trigger: str
    conditions: tuple[Condition, ...] = ()
    actions: tuple[ActionSpec, ...] = ()
    enabled: bool = True


def evaluate_condition(condition: Condition, payload: dict[str, Any]) -> bool:
    """Return whether *condition* holds for *payload*.

    Supported ops: ``eq``, ``ne``, ``contains``, ``startswith``, ``endswith``,
    ``gt``, ``lt``, ``exists``. A condition referencing an absent field is
    ``False`` for every op except ``exists`` (which reports presence) -- so a
    rule never crashes on an event that simply lacks the field.
    """
    present = condition.field in payload
    if condition.op == "exists":
        return present is bool(condition.value if condition.value is not None else True)
    if not present:
        return False
    actual = payload[condition.field]
    expected = condition.value
    try:
        match condition.op:
            case "eq":
                return bool(actual == expected)
            case "ne":
                return bool(actual != expected)
            case "contains":
                return str(expected) in str(actual)
            case "startswith":
                return str(actual).startswith(str(expected))
            case "endswith":
                return str(actual).endswith(str(expected))
            case "gt":
                return bool(actual > expected)
            case "lt":
                return bool(actual < expected)
            case _:
                raise AutomationError(f"unknown condition op: {condition.op!r}")
    except TypeError:
        # e.g. comparing incompatible types with gt/lt -> condition simply
        # doesn't hold rather than blowing up the whole event dispatch.
        return False


class ActionRegistry:
    """Maps action-type names to the callables that perform them."""

    def __init__(self) -> None:
        self._actions: dict[str, ActionFn] = {}

    def register(self, name: str, action: ActionFn) -> None:
        """Register *action* under *name*, replacing any prior registration."""
        self._actions[name] = action

    def get(self, name: str) -> ActionFn:
        try:
            return self._actions[name]
        except KeyError:
            raise AutomationError(f"no action registered as {name!r}") from None

    def has(self, name: str) -> bool:
        return name in self._actions

    def names(self) -> list[str]:
        return sorted(self._actions)


class RuleEngine:
    """Subscribes to the event bus and runs rule actions on matching events."""

    def __init__(self, events: EventBus, actions: ActionRegistry) -> None:
        self._events = events
        self._actions = actions
        self._rules: dict[str, Rule] = {}
        self._subscriptions: dict[str, Callable[[], None]] = {}

    def add_rule(self, rule: Rule) -> None:
        """Register *rule* and subscribe to its trigger topic.

        Subscriptions are per-trigger and reference-counted implicitly: the
        engine keeps one handler per trigger topic and dispatches to all
        rules sharing it, so adding many rules for one event doesn't stack
        redundant handlers on the bus.
        """
        self._rules[rule.name] = rule
        if rule.trigger not in self._subscriptions:
            unsubscribe = self._events.subscribe(rule.trigger, self._make_handler(rule.trigger))
            self._subscriptions[rule.trigger] = unsubscribe

    def remove_rule(self, name: str) -> None:
        self._rules.pop(name, None)

    def rule_names(self) -> list[str]:
        return sorted(self._rules)

    def clear(self) -> None:
        """Remove all rules and unsubscribe from the bus."""
        for unsubscribe in self._subscriptions.values():
            unsubscribe()
        self._subscriptions.clear()
        self._rules.clear()

    def _make_handler(self, trigger: str) -> Callable[[Event], None]:
        def handle(event: Event) -> None:
            for rule in list(self._rules.values()):
                if rule.trigger != trigger or not rule.enabled:
                    continue
                if all(evaluate_condition(c, event.payload) for c in rule.conditions):
                    self._run_actions(rule, event)

        return handle

    def _run_actions(self, rule: Rule, event: Event) -> None:
        for spec in rule.actions:
            try:
                self._actions.get(spec.type)(event, spec.params)
            except AutomationError:
                _logger.warning("rule %r references unknown action %r", rule.name, spec.type)
            except Exception:
                _logger.exception("action %r in rule %r failed", spec.type, rule.name)
