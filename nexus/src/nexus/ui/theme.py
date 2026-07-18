"""Dark and light themes as Qt style sheets, with a small theme manager.

Themes are plain QSS strings applied to the whole ``QApplication``, so every
widget picks them up without per-widget styling code. :class:`ThemeManager`
tracks the current theme, applies it, and can toggle -- the main window wires
a menu action and a keyboard shortcut to :meth:`ThemeManager.toggle`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from nexus.core.logging import get_logger

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication

__all__ = ["ThemeManager", "available_themes", "stylesheet_for"]

_logger = get_logger("ui.theme")

_DARK = """
* { font-family: "Segoe UI", "Helvetica Neue", sans-serif; font-size: 10pt; }
QWidget { background-color: #1e1f22; color: #e6e6e6; }
QMainWindow, QDialog { background-color: #1e1f22; }
QMenuBar, QToolBar { background-color: #2b2d31; border: none; }
QMenuBar::item:selected, QMenu::item:selected { background-color: #3a7bd5; }
QMenu { background-color: #2b2d31; border: 1px solid #3a3c40; }
QDockWidget { titlebar-close-icon: none; color: #e6e6e6; }
QDockWidget::title { background-color: #2b2d31; padding: 6px; }
QLineEdit, QTextEdit, QPlainTextEdit, QListWidget, QListView, QTreeView, QTableView, QComboBox {
    background-color: #26272b; border: 1px solid #3a3c40; border-radius: 4px; padding: 4px;
    selection-background-color: #3a7bd5;
}
QPushButton {
    background-color: #3a7bd5; color: white; border: none; border-radius: 4px; padding: 6px 12px;
}
QPushButton:hover { background-color: #4a8be5; }
QPushButton:disabled { background-color: #44464b; color: #888; }
QTabBar::tab { background: #2b2d31; padding: 6px 12px; border-radius: 4px; }
QTabBar::tab:selected { background: #3a7bd5; }
QScrollBar:vertical { background: #26272b; width: 12px; }
QScrollBar::handle:vertical { background: #44464b; border-radius: 6px; }
QStatusBar { background-color: #2b2d31; }
"""

_LIGHT = """
* { font-family: "Segoe UI", "Helvetica Neue", sans-serif; font-size: 10pt; }
QWidget { background-color: #f5f5f7; color: #1a1a1a; }
QMainWindow, QDialog { background-color: #f5f5f7; }
QMenuBar, QToolBar { background-color: #e8e8ec; border: none; }
QMenuBar::item:selected, QMenu::item:selected { background-color: #3a7bd5; color: white; }
QMenu { background-color: #ffffff; border: 1px solid #d0d0d5; }
QDockWidget::title { background-color: #e8e8ec; padding: 6px; }
QLineEdit, QTextEdit, QPlainTextEdit, QListWidget, QListView, QTreeView, QTableView, QComboBox {
    background-color: #ffffff; border: 1px solid #d0d0d5; border-radius: 4px; padding: 4px;
    selection-background-color: #3a7bd5; selection-color: white;
}
QPushButton {
    background-color: #3a7bd5; color: white; border: none; border-radius: 4px; padding: 6px 12px;
}
QPushButton:hover { background-color: #2f6bc0; }
QPushButton:disabled { background-color: #c0c0c8; color: #eee; }
QTabBar::tab { background: #e8e8ec; padding: 6px 12px; border-radius: 4px; }
QTabBar::tab:selected { background: #3a7bd5; color: white; }
QStatusBar { background-color: #e8e8ec; }
"""

_THEMES = {"dark": _DARK, "light": _LIGHT}


def available_themes() -> list[str]:
    """Return the names of the built-in themes."""
    return sorted(_THEMES)


def stylesheet_for(theme: str) -> str:
    """Return the QSS for *theme*, falling back to dark for an unknown name."""
    return _THEMES.get(theme, _DARK)


class ThemeManager:
    """Applies and toggles the application theme."""

    def __init__(self, app: QApplication, initial: str = "dark") -> None:
        self._app = app
        self._current = initial if initial in _THEMES else "dark"
        self.apply(self._current)

    @property
    def current(self) -> str:
        return self._current

    def apply(self, theme: str) -> None:
        """Apply *theme* to the whole application."""
        self._current = theme if theme in _THEMES else "dark"
        self._app.setStyleSheet(stylesheet_for(self._current))
        _logger.debug("applied theme %r", self._current)

    def toggle(self) -> str:
        """Switch between dark and light; return the new theme name."""
        self.apply("light" if self._current == "dark" else "dark")
        return self._current
