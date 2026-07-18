"""Built-in rule actions and a default :class:`ActionRegistry`.

These are the actions a workflow rule can run out of the box. They are
deliberately safe and side-effect-light -- writing to the log and raising an
in-app notification event -- so enabling automation can never damage a
user's files or data. Registering a new action (move a file, call a webhook)
is a matter of adding one function here or from a plugin; the rule engine
picks it up by name with no changes of its own.
"""

from __future__ import annotations

from typing import Any

from nexus.automation.rules import ActionRegistry
from nexus.core.events import Event, EventBus
from nexus.core.logging import get_logger

__all__ = ["NOTIFICATION_TOPIC", "default_action_registry"]

_logger = get_logger("automation.actions")

#: Topic used by the ``notify`` action; the UI status bar subscribes to it.
NOTIFICATION_TOPIC = "notification.raised"


def default_action_registry(events: EventBus) -> ActionRegistry:
    """Return an :class:`ActionRegistry` with Nexus's built-in actions.

    * ``log`` -- write ``params['message']`` (or the event topic) to the log.
    * ``notify`` -- publish a :data:`NOTIFICATION_TOPIC` event carrying a
      message, which the main window shows in its status bar.
    * ``noop`` -- do nothing; handy as a placeholder while building a rule.
    """
    registry = ActionRegistry()

    def log_action(event: Event, params: dict[str, Any]) -> None:
        message = str(params.get("message", event.name))
        _logger.info("rule action: %s (from %s)", message, event.name)

    def notify_action(event: Event, params: dict[str, Any]) -> None:
        message = str(params.get("message", f"Triggered by {event.name}"))
        events.publish(NOTIFICATION_TOPIC, message=message, trigger=event.name)

    def noop_action(event: Event, params: dict[str, Any]) -> None:
        return None

    registry.register("log", log_action)
    registry.register("notify", notify_action)
    registry.register("noop", noop_action)
    return registry
