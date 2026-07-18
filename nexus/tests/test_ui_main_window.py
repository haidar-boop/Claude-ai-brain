"""Widget tests for the main window shell and the settings dialog."""

from __future__ import annotations

from typing import Any

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox
from pytestqt.qtbot import QtBot

from nexus.automation.actions import NOTIFICATION_TOPIC
from nexus.ui.dialogs.settings_dialog import SettingsDialog
from nexus.ui.main_window import MainWindow
from nexus.ui.theme import ThemeManager


@pytest.fixture(autouse=True)
def _no_modal_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    ok = QMessageBox.StandardButton.Ok
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: ok)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: ok)
    monkeypatch.setattr(QMessageBox, "about", lambda *a, **k: None)


def _window(qtbot: QtBot, qapp: QApplication, app_ctx: Any) -> MainWindow:
    manager = ThemeManager(qapp, initial="dark")
    window = MainWindow(app_ctx, manager)
    qtbot.addWidget(window)
    return window


def test_main_window_builds_all_docks(qtbot: QtBot, qapp: QApplication, app_ctx: Any) -> None:
    window = _window(qtbot, qapp, app_ctx)
    assert set(window._docks) == {"notes", "tasks", "calendar", "files", "ai", "automation"}
    # Every shortcut id has a bound action.
    from nexus.ui.shortcuts import SHORTCUTS

    assert set(window._actions) == set(SHORTCUTS)


def test_theme_toggle_action(qtbot: QtBot, qapp: QApplication, app_ctx: Any) -> None:
    window = _window(qtbot, qapp, app_ctx)
    window._on_toggle_theme()
    assert window._theme_manager.current == "light"


def test_notification_reaches_status_bar(qtbot: QtBot, qapp: QApplication, app_ctx: Any) -> None:
    window = _window(qtbot, qapp, app_ctx)
    app_ctx.events.publish(NOTIFICATION_TOPIC, message="a folder changed")
    assert window.statusBar().currentMessage() == "a folder changed"


def test_refresh_all_panels(qtbot: QtBot, qapp: QApplication, app_ctx: Any) -> None:
    app_ctx.notes.create("N")
    window = _window(qtbot, qapp, app_ctx)
    window._on_refresh()
    assert "Refreshed" in window.statusBar().currentMessage()


def test_focus_panel_raises_dock(qtbot: QtBot, qapp: QApplication, app_ctx: Any) -> None:
    window = _window(qtbot, qapp, app_ctx)
    window._focus_panel("files")  # dock
    window._focus_panel("dashboard")  # central widget, different code path
    # The window itself is never shown in the test, so isVisible() is False
    # up the whole ancestor chain; isHidden() reflects that focus un-hid the
    # dock (raised its tab) regardless of the top-level window's state.
    assert not window._docks["files"].isHidden()


def test_backup_in_memory_is_handled(qtbot: QtBot, qapp: QApplication, app_ctx: Any) -> None:
    window = _window(qtbot, qapp, app_ctx)
    # In-memory database has no backup location; the handler must not raise.
    window._on_backup()


def test_close_unsubscribes(qtbot: QtBot, qapp: QApplication, app_ctx: Any) -> None:
    window = _window(qtbot, qapp, app_ctx)
    window.close()
    # After close, a published notification must not reach a torn-down bridge.
    app_ctx.events.publish(NOTIFICATION_TOPIC, message="late")


def test_settings_dialog_live_apply_and_revert(
    qtbot: QtBot, qapp: QApplication, app_ctx: Any
) -> None:
    manager = ThemeManager(qapp, initial="dark")
    dialog = SettingsDialog(app_ctx, manager)
    qtbot.addWidget(dialog)

    dialog._theme.setCurrentText("light")
    assert manager.current == "light"  # applied live for preview

    dialog._on_reject()
    assert manager.current == "dark"  # reverted to the theme active on open
