"""A small plugin system: discover, activate, and deactivate extensions.

A Nexus plugin is any object exposing a ``name`` and an ``activate(context)``
method (and, optionally, ``deactivate()``). On activation it receives the
live :class:`~nexus.app_context.AppContext`, which is all the extension
surface it needs: subscribe to the event bus, register new automation actions
on ``context.automation_actions``, or call any service. Plugins are
discovered from the ``nexus.plugins`` entry-point group *or* registered
directly, so a third party ships a plugin as an ordinary installable package
without Nexus having to know about it in advance.
"""

from __future__ import annotations

from nexus.plugins.base import NexusPlugin
from nexus.plugins.manager import PluginManager

__all__ = ["NexusPlugin", "PluginManager"]
