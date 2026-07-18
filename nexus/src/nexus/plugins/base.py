"""The plugin contract.

Kept intentionally tiny: a plugin needs a stable ``name`` (for logging and
de-duplication) and an ``activate`` method that is handed the running
:class:`~nexus.app_context.AppContext`. Everything a plugin might want to do
-- react to events, add automation actions, seed data -- is reachable from
that context, so the interface never has to grow a method per capability.

``deactivate`` is optional; the manager calls it only if the plugin defines
one, so simple plugins can omit it entirely.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from nexus.app_context import AppContext

__all__ = ["NexusPlugin"]


@runtime_checkable
class NexusPlugin(Protocol):
    """The minimal interface a Nexus plugin must satisfy."""

    name: str

    def activate(self, context: AppContext) -> None:
        """Wire the plugin into the running application.

        Called once, after the context and all services exist. Register event
        subscriptions, automation actions, or anything else here.
        """
        ...
