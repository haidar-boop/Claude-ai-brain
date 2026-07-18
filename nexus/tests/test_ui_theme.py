"""Tests for the theme manager and the shortcuts table."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from nexus.ui.shortcuts import SHORTCUTS, shortcuts_help_text
from nexus.ui.theme import ThemeManager, available_themes, stylesheet_for


def test_available_themes() -> None:
    assert available_themes() == ["dark", "light"]


def test_stylesheet_for_known_and_unknown() -> None:
    assert "background-color" in stylesheet_for("dark")
    # Unknown themes fall back to dark rather than returning empty QSS.
    assert stylesheet_for("nonsense") == stylesheet_for("dark")


def test_theme_manager_applies_and_toggles(qapp: QApplication) -> None:
    manager = ThemeManager(qapp, initial="dark")
    assert manager.current == "dark"
    assert qapp.styleSheet() == stylesheet_for("dark")

    new_theme = manager.toggle()
    assert new_theme == "light"
    assert manager.current == "light"
    assert qapp.styleSheet() == stylesheet_for("light")

    manager.toggle()
    assert manager.current == "dark"


def test_theme_manager_rejects_unknown_initial(qapp: QApplication) -> None:
    manager = ThemeManager(qapp, initial="bogus")
    assert manager.current == "dark"


def test_shortcuts_help_lists_every_shortcut() -> None:
    text = shortcuts_help_text()
    for spec in SHORTCUTS.values():
        assert spec.key in text
        assert spec.label in text


def test_shortcut_keys_are_unique() -> None:
    keys = [spec.key for spec in SHORTCUTS.values()]
    assert len(keys) == len(set(keys))
