"""Discover, activate, and deactivate plugins.

Discovery reads the ``nexus.plugins`` entry-point group; each entry may point
at a plugin instance, or a class/factory that the manager instantiates. A
broken entry point is logged and skipped rather than taking the whole app
down -- one bad third-party package should not stop Nexus from starting.
Plugins can also be registered directly, which is what tests use and what an
embedding application does when it wants explicit control.
"""

from __future__ import annotations

from importlib import metadata
from typing import TYPE_CHECKING

from nexus.core.errors import PluginError
from nexus.core.logging import get_logger
from nexus.plugins.base import NexusPlugin

if TYPE_CHECKING:
    from nexus.app_context import AppContext

__all__ = ["PluginManager"]

_logger = get_logger("plugins")

ENTRY_POINT_GROUP = "nexus.plugins"


class PluginManager:
    """Owns the set of plugins for one application and their lifecycle."""

    def __init__(self, context: AppContext, *, entry_point_group: str = ENTRY_POINT_GROUP) -> None:
        self._context = context
        self._group = entry_point_group
        self._plugins: list[NexusPlugin] = []
        self._activated: list[NexusPlugin] = []

    @property
    def plugins(self) -> tuple[NexusPlugin, ...]:
        """The registered plugins, in registration order."""
        return tuple(self._plugins)

    def register(self, plugin: NexusPlugin) -> None:
        """Register a plugin instance directly (skips duplicates by name)."""
        if not isinstance(plugin, NexusPlugin):
            raise PluginError(f"{plugin!r} is not a valid plugin (needs a 'name' and 'activate')")
        if any(existing.name == plugin.name for existing in self._plugins):
            _logger.debug("plugin %r already registered; skipping", plugin.name)
            return
        self._plugins.append(plugin)

    def discover(self) -> list[str]:
        """Load plugins from the entry-point group; return the names loaded."""
        loaded: list[str] = []
        for entry in metadata.entry_points(group=self._group):
            try:
                obj = entry.load()
                plugin = obj() if isinstance(obj, type) else obj
                self.register(plugin)
                loaded.append(plugin.name)
            except Exception:
                # A single malformed plugin must not stop discovery.
                _logger.exception("failed to load plugin entry point %r", entry.name)
        return loaded

    def activate_all(self) -> None:
        """Activate every registered plugin that is not already active."""
        for plugin in self._plugins:
            if plugin in self._activated:
                continue
            try:
                plugin.activate(self._context)
                self._activated.append(plugin)
                _logger.info("activated plugin %r", plugin.name)
            except Exception:
                _logger.exception("plugin %r failed to activate", plugin.name)

    def deactivate_all(self) -> None:
        """Deactivate active plugins in reverse order (best-effort)."""
        for plugin in reversed(self._activated):
            deactivate = getattr(plugin, "deactivate", None)
            if callable(deactivate):
                try:
                    deactivate()
                except Exception:
                    _logger.exception("plugin %r failed to deactivate", plugin.name)
        self._activated.clear()
