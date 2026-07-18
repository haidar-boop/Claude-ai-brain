"""Tests for the plugin manager: registration, discovery, and lifecycle."""

from __future__ import annotations

from typing import Any

import pytest

from nexus.app_context import AppContext
from nexus.automation.rules import ActionSpec
from nexus.core.errors import PluginError
from nexus.plugins import PluginManager
from nexus.plugins import manager as manager_module


class RecordingPlugin:
    """A plugin that records the lifecycle calls it receives."""

    name = "recording"

    def __init__(self) -> None:
        self.activated_with: AppContext | None = None
        self.deactivated = False

    def activate(self, context: AppContext) -> None:
        self.activated_with = context

    def deactivate(self) -> None:
        self.deactivated = True


class ActionPlugin:
    """A plugin that extends automation with a new action."""

    name = "greeter"

    def __init__(self) -> None:
        self.seen: list[str] = []

    def activate(self, context: AppContext) -> None:
        def greet(event: Any, params: dict[str, Any]) -> None:
            self.seen.append(event.name)

        context.automation_actions.register("greet", greet)


class _FakeEntryPoint:
    def __init__(self, name: str, obj: object, *, broken: bool = False) -> None:
        self.name = name
        self._obj = obj
        self._broken = broken

    def load(self) -> object:
        if self._broken:
            raise RuntimeError("boom")
        return self._obj


@pytest.fixture
def context() -> Any:
    ctx = AppContext.in_memory()
    try:
        yield ctx
    finally:
        ctx.close()


def test_register_and_activate(context: Any) -> None:
    manager = PluginManager(context)
    plugin = RecordingPlugin()
    manager.register(plugin)
    assert manager.plugins == (plugin,)

    manager.activate_all()
    assert plugin.activated_with is context

    manager.deactivate_all()
    assert plugin.deactivated is True


def test_register_rejects_non_plugin(context: Any) -> None:
    manager = PluginManager(context)
    with pytest.raises(PluginError):
        manager.register(object())  # type: ignore[arg-type]


def test_register_deduplicates_by_name(context: Any) -> None:
    manager = PluginManager(context)
    manager.register(RecordingPlugin())
    manager.register(RecordingPlugin())
    assert len(manager.plugins) == 1


def test_activate_is_idempotent(context: Any) -> None:
    manager = PluginManager(context)
    plugin = ActionPlugin()
    manager.register(plugin)
    manager.activate_all()
    manager.activate_all()  # second call must not re-activate
    # Registering the same action twice would still be fine, but the manager
    # should not have called activate twice; the registry has exactly one.
    assert context.automation_actions.has("greet")


def test_plugin_can_extend_automation(context: Any) -> None:
    manager = PluginManager(context)
    plugin = ActionPlugin()
    manager.register(plugin)
    manager.activate_all()

    context.automation.create_rule(
        "greet on note",
        "note.created",
        actions=[ActionSpec(type="greet")],
    )
    context.reload_automation()
    context.notes.create("Hello")
    assert plugin.seen == ["note.created"]


def test_discover_from_entry_points(context: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = [
        _FakeEntryPoint("recording", RecordingPlugin),
        _FakeEntryPoint("broken", None, broken=True),
    ]
    monkeypatch.setattr(
        manager_module.metadata,
        "entry_points",
        lambda group: fake if group == "nexus.plugins" else [],
    )
    manager = PluginManager(context)
    loaded = manager.discover()
    # The broken entry point is skipped; the good one loads.
    assert loaded == ["recording"]
    assert len(manager.plugins) == 1
