"""Keyboard shortcuts, defined once so the window and help stay in sync.

Every shortcut the app binds is listed in :data:`SHORTCUTS` as an ordered
mapping from a stable action id to its label and key sequence. The main
window binds actions by looking these up, and the "Keyboard shortcuts" help
uses the same table -- so what a key does and what the help says it does can
never drift apart.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass

__all__ = ["SHORTCUTS", "ShortcutSpec", "shortcuts_help_text"]


@dataclass(frozen=True, slots=True)
class ShortcutSpec:
    """A user-visible label and the key sequence that triggers it."""

    label: str
    key: str


SHORTCUTS: OrderedDict[str, ShortcutSpec] = OrderedDict(
    (
        ("focus_dashboard", ShortcutSpec("Show Dashboard", "Ctrl+1")),
        ("focus_notes", ShortcutSpec("Show Notes", "Ctrl+2")),
        ("focus_tasks", ShortcutSpec("Show Tasks", "Ctrl+3")),
        ("focus_files", ShortcutSpec("Show Files", "Ctrl+4")),
        ("focus_ai", ShortcutSpec("Show AI Assistant", "Ctrl+5")),
        ("focus_calendar", ShortcutSpec("Show Calendar", "Ctrl+6")),
        ("focus_automation", ShortcutSpec("Show Automation", "Ctrl+7")),
        ("toggle_theme", ShortcutSpec("Toggle dark / light theme", "Ctrl+T")),
        ("settings", ShortcutSpec("Open Settings", "Ctrl+,")),
        ("refresh", ShortcutSpec("Refresh current panel", "F5")),
        ("quit", ShortcutSpec("Quit Nexus", "Ctrl+Q")),
    )
)


def shortcuts_help_text() -> str:
    """Return an aligned, human-readable list of every shortcut."""
    width = max(len(spec.key) for spec in SHORTCUTS.values())
    lines = [f"{spec.key.ljust(width)}   {spec.label}" for spec in SHORTCUTS.values()]
    return "\n".join(lines)
