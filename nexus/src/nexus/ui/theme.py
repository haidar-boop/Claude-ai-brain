"""Dark and light themes as Qt style sheets, with a small theme manager.

Themes are plain QSS strings applied to the whole ``QApplication``, so every
widget picks them up without per-widget styling code. Both themes share one
design: a cyan-to-violet neon accent (``#22d3ee`` -> ``#a855f7``) on flat,
sharply rounded panels -- dark runs it on a near-black "void" for a HUD/
sci-fi console feel, light runs the same accent on crisp white for a clean
"glass" look in bright rooms. :class:`ThemeManager` tracks the current theme,
applies it, and can toggle -- the main window wires a menu action and a
keyboard shortcut to :meth:`ThemeManager.toggle`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from nexus.core.logging import get_logger

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication

__all__ = ["ThemeManager", "available_themes", "stylesheet_for"]

_logger = get_logger("ui.theme")

_FONT = '"Inter", "Segoe UI", "Helvetica Neue", sans-serif'

_ACCENT = "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #06b6d4, stop:1 #7c3aed)"
_ACCENT_HOVER = "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #22d3ee, stop:1 #a855f7)"
_ACCENT_PRESSED = "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0891b2, stop:1 #6d28d9)"

_DARK = f"""
* {{
    font-family: {_FONT};
    font-size: 10pt;
    outline: none;
}}

QWidget {{ background-color: #0a0e16; color: #e6f1ff; }}
QMainWindow, QDialog {{ background-color: #0a0e16; }}

QMenuBar, QToolBar {{
    background-color: #0d1420;
    border: none;
    border-bottom: 1px solid #1e2c44;
    spacing: 4px;
}}
QMenuBar::item {{ background: transparent; padding: 6px 10px; border-radius: 4px; }}
QMenuBar::item:selected {{ background-color: rgba(34, 211, 238, 40); color: #22d3ee; }}
QMenu {{ background-color: #10182a; border: 1px solid #22d3ee; border-radius: 6px; padding: 4px; }}
QMenu::item {{ padding: 6px 24px; border-radius: 4px; }}
QMenu::item:selected {{ background-color: rgba(34, 211, 238, 45); color: #e6f1ff; }}
QMenu::separator {{ height: 1px; background: #1e2c44; margin: 4px 8px; }}

QDockWidget {{ titlebar-close-icon: none; color: #e6f1ff; }}
QDockWidget::title {{
    background-color: #0d1420;
    padding: 8px;
    font-weight: 600;
    color: #7dd3fc;
    border-bottom: 2px solid #1e2c44;
}}

QLineEdit, QTextEdit, QPlainTextEdit,
QListWidget, QListView, QTreeView, QTableView, QComboBox {{
    background-color: #10182a;
    border: 1px solid #1e2c44;
    border-radius: 6px;
    padding: 5px;
    selection-background-color: #22d3ee;
    selection-color: #05131f;
    color: #e6f1ff;
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{
    border: 1px solid #22d3ee;
}}
QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {{ color: #4a5872; }}
QAbstractItemView::item {{ padding: 4px 6px; border-radius: 4px; }}
QListWidget::item:hover, QListView::item:hover, QTreeView::item:hover {{
    background-color: rgba(34, 211, 238, 22);
}}
QListWidget::indicator, QCheckBox::indicator, QRadioButton::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid #22d3ee;
    border-radius: 3px;
    background-color: #0a0e16;
}}
QListWidget::indicator:checked, QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background-color: #22d3ee;
}}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background-color: #10182a;
    border: 1px solid #22d3ee;
    border-radius: 6px;
    selection-background-color: #22d3ee;
    selection-color: #05131f;
    outline: none;
}}

QPushButton {{
    background: {_ACCENT};
    color: white;
    border: none;
    border-radius: 6px;
    padding: 7px 16px;
    font-weight: 600;
}}
QPushButton:hover {{ background: {_ACCENT_HOVER}; }}
QPushButton:pressed {{ background: {_ACCENT_PRESSED}; }}
QPushButton:disabled {{ background: #1a2438; color: #4a5872; }}

QTabWidget::pane {{ border: 1px solid #1e2c44; border-radius: 6px; top: -1px; }}
QTabBar::tab {{
    background-color: #10182a;
    color: #7488a8;
    padding: 8px 16px;
    margin-right: 2px;
    border: 1px solid #1e2c44;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}}
QTabBar::tab:selected {{
    background-color: #16233a;
    color: #22d3ee;
    border-color: #22d3ee;
    border-bottom: 2px solid #22d3ee;
    font-weight: 600;
}}
QTabBar::tab:hover:!selected {{ color: #e6f1ff; }}

QScrollBar:vertical {{ background: #0a0e16; width: 11px; margin: 0; border-radius: 5px; }}
QScrollBar::handle:vertical {{ background-color: #233350; border-radius: 5px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background-color: #22d3ee; }}
QScrollBar:horizontal {{ background: #0a0e16; height: 11px; margin: 0; border-radius: 5px; }}
QScrollBar::handle:horizontal {{ background-color: #233350; border-radius: 5px; min-width: 24px; }}
QScrollBar::handle:horizontal:hover {{ background-color: #22d3ee; }}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0; width: 0; background: none; border: none;
}}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

QSplitter::handle {{ background-color: #1e2c44; }}
QSplitter::handle:hover {{ background-color: #22d3ee; }}
QSplitter::handle:horizontal {{ width: 2px; }}
QSplitter::handle:vertical {{ height: 2px; }}

QGroupBox {{
    border: 1px solid #1e2c44;
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 12px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 6px;
    color: #22d3ee;
}}

QProgressBar {{
    background-color: #10182a;
    border: 1px solid #1e2c44;
    border-radius: 5px;
    text-align: center;
    color: #e6f1ff;
}}
QProgressBar::chunk {{ border-radius: 5px; background: {_ACCENT}; }}

QFrame#statCard {{
    background-color: #101a2e;
    border: 1px solid #1e2c44;
    border-radius: 10px;
    padding: 2px;
}}
QFrame#statCard:hover {{ border: 1px solid #22d3ee; }}
QLabel#statValue {{ color: #22d3ee; }}

QCalendarWidget QAbstractItemView:enabled {{
    background-color: #10182a;
    color: #e6f1ff;
    selection-background-color: #22d3ee;
    selection-color: #05131f;
    outline: none;
}}
QCalendarWidget QAbstractItemView:disabled {{ color: #3a4a68; }}
QCalendarWidget QWidget#qt_calendar_navigationbar {{
    background-color: #0d1420;
    border-bottom: 1px solid #1e2c44;
}}
QCalendarWidget QToolButton {{
    color: #e6f1ff;
    background-color: transparent;
    border: none;
    border-radius: 4px;
    padding: 4px 8px;
    font-weight: 600;
}}
QCalendarWidget QToolButton:hover {{ background-color: rgba(34, 211, 238, 35); color: #22d3ee; }}
QCalendarWidget QSpinBox {{
    background-color: #10182a;
    color: #e6f1ff;
    border: 1px solid #1e2c44;
    border-radius: 4px;
}}
QCalendarWidget QMenu {{ background-color: #10182a; border: 1px solid #22d3ee; }}

QHeaderView::section {{
    background-color: #0d1420;
    color: #7dd3fc;
    padding: 4px;
    border: none;
    border-bottom: 1px solid #1e2c44;
    font-weight: 600;
}}

QToolTip {{
    background-color: #10182a;
    color: #e6f1ff;
    border: 1px solid #22d3ee;
    padding: 4px 8px;
    border-radius: 4px;
}}
QStatusBar {{ background-color: #0d1420; border-top: 1px solid #1e2c44; color: #7dd3fc; }}
"""

_LIGHT = f"""
* {{
    font-family: {_FONT};
    font-size: 10pt;
    outline: none;
}}

QWidget {{ background-color: #eef3fb; color: #0f172a; }}
QMainWindow, QDialog {{ background-color: #eef3fb; }}

QMenuBar, QToolBar {{
    background-color: #ffffff;
    border: none;
    border-bottom: 1px solid #d3ddec;
    spacing: 4px;
}}
QMenuBar::item {{ background: transparent; padding: 6px 10px; border-radius: 4px; }}
QMenuBar::item:selected {{ background-color: rgba(14, 165, 233, 30); color: #0284c7; }}
QMenu {{ background-color: #ffffff; border: 1px solid #0ea5e9; border-radius: 6px; padding: 4px; }}
QMenu::item {{ padding: 6px 24px; border-radius: 4px; }}
QMenu::item:selected {{ background-color: rgba(14, 165, 233, 30); color: #0f172a; }}
QMenu::separator {{ height: 1px; background: #d3ddec; margin: 4px 8px; }}

QDockWidget {{ titlebar-close-icon: none; color: #0f172a; }}
QDockWidget::title {{
    background-color: #ffffff;
    padding: 8px;
    font-weight: 600;
    color: #0284c7;
    border-bottom: 2px solid #d3ddec;
}}

QLineEdit, QTextEdit, QPlainTextEdit,
QListWidget, QListView, QTreeView, QTableView, QComboBox {{
    background-color: #ffffff;
    border: 1px solid #d3ddec;
    border-radius: 6px;
    padding: 5px;
    selection-background-color: #0ea5e9;
    selection-color: #ffffff;
    color: #0f172a;
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{
    border: 1px solid #0ea5e9;
}}
QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {{ color: #9aa7bd; }}
QAbstractItemView::item {{ padding: 4px 6px; border-radius: 4px; }}
QListWidget::item:hover, QListView::item:hover, QTreeView::item:hover {{
    background-color: rgba(14, 165, 233, 18);
}}
QListWidget::indicator, QCheckBox::indicator, QRadioButton::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid #0ea5e9;
    border-radius: 3px;
    background-color: #ffffff;
}}
QListWidget::indicator:checked, QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background-color: #0ea5e9;
}}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background-color: #ffffff;
    border: 1px solid #0ea5e9;
    border-radius: 6px;
    selection-background-color: #0ea5e9;
    selection-color: #ffffff;
    outline: none;
}}

QPushButton {{
    background: {_ACCENT};
    color: white;
    border: none;
    border-radius: 6px;
    padding: 7px 16px;
    font-weight: 600;
}}
QPushButton:hover {{ background: {_ACCENT_HOVER}; }}
QPushButton:pressed {{ background: {_ACCENT_PRESSED}; }}
QPushButton:disabled {{ background: #d3ddec; color: #9aa7bd; }}

QTabWidget::pane {{ border: 1px solid #d3ddec; border-radius: 6px; top: -1px; }}
QTabBar::tab {{
    background-color: #ffffff;
    color: #64748b;
    padding: 8px 16px;
    margin-right: 2px;
    border: 1px solid #d3ddec;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}}
QTabBar::tab:selected {{
    background-color: #f3f8ff;
    color: #0284c7;
    border-color: #0ea5e9;
    border-bottom: 2px solid #0ea5e9;
    font-weight: 600;
}}
QTabBar::tab:hover:!selected {{ color: #0f172a; }}

QScrollBar:vertical {{ background: #eef3fb; width: 11px; margin: 0; border-radius: 5px; }}
QScrollBar::handle:vertical {{ background-color: #c7d2e3; border-radius: 5px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background-color: #0ea5e9; }}
QScrollBar:horizontal {{ background: #eef3fb; height: 11px; margin: 0; border-radius: 5px; }}
QScrollBar::handle:horizontal {{ background-color: #c7d2e3; border-radius: 5px; min-width: 24px; }}
QScrollBar::handle:horizontal:hover {{ background-color: #0ea5e9; }}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0; width: 0; background: none; border: none;
}}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

QSplitter::handle {{ background-color: #d3ddec; }}
QSplitter::handle:hover {{ background-color: #0ea5e9; }}
QSplitter::handle:horizontal {{ width: 2px; }}
QSplitter::handle:vertical {{ height: 2px; }}

QGroupBox {{
    border: 1px solid #d3ddec;
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 12px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 6px;
    color: #0284c7;
}}

QProgressBar {{
    background-color: #ffffff;
    border: 1px solid #d3ddec;
    border-radius: 5px;
    text-align: center;
    color: #0f172a;
}}
QProgressBar::chunk {{ border-radius: 5px; background: {_ACCENT}; }}

QFrame#statCard {{
    background-color: #ffffff;
    border: 1px solid #d3ddec;
    border-radius: 10px;
    padding: 2px;
}}
QFrame#statCard:hover {{ border: 1px solid #0ea5e9; }}
QLabel#statValue {{ color: #0284c7; }}

QCalendarWidget QAbstractItemView:enabled {{
    background-color: #ffffff;
    color: #0f172a;
    selection-background-color: #0ea5e9;
    selection-color: #ffffff;
    outline: none;
}}
QCalendarWidget QAbstractItemView:disabled {{ color: #b7c2d6; }}
QCalendarWidget QWidget#qt_calendar_navigationbar {{
    background-color: #ffffff;
    border-bottom: 1px solid #d3ddec;
}}
QCalendarWidget QToolButton {{
    color: #0f172a;
    background-color: transparent;
    border: none;
    border-radius: 4px;
    padding: 4px 8px;
    font-weight: 600;
}}
QCalendarWidget QToolButton:hover {{ background-color: rgba(14, 165, 233, 25); color: #0284c7; }}
QCalendarWidget QSpinBox {{
    background-color: #ffffff;
    color: #0f172a;
    border: 1px solid #d3ddec;
    border-radius: 4px;
}}
QCalendarWidget QMenu {{ background-color: #ffffff; border: 1px solid #0ea5e9; }}

QHeaderView::section {{
    background-color: #ffffff;
    color: #0284c7;
    padding: 4px;
    border: none;
    border-bottom: 1px solid #d3ddec;
    font-weight: 600;
}}

QToolTip {{
    background-color: #ffffff;
    color: #0f172a;
    border: 1px solid #0ea5e9;
    padding: 4px 8px;
    border-radius: 4px;
}}
QStatusBar {{ background-color: #ffffff; border-top: 1px solid #d3ddec; color: #0284c7; }}
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
