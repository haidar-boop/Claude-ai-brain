"""The main window: a dashboard centre with dockable module panels.

The overview :class:`~nexus.ui.panels.dashboard_panel.DashboardPanel` sits in
the centre; every other module is a ``QDockWidget`` tabbed together on the
right, so the user can float, stack, or hide any of them. Menus, a toolbar,
and the shortcuts from :mod:`nexus.ui.shortcuts` all drive the same actions.

Automation runs on background threads (folder watching, the scheduler), so
its notifications reach the status bar through a ``Signal`` on
:class:`_NotificationBridge`: the event handler only emits, and Qt marshals
the actual status-bar update onto the UI thread. That keeps every widget
touch on the GUI thread, which Qt requires.
"""

from __future__ import annotations

from types import TracebackType

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QDockWidget,
    QMainWindow,
    QMessageBox,
    QWidget,
)

from nexus.app_context import AppContext
from nexus.automation.actions import NOTIFICATION_TOPIC
from nexus.core.errors import NexusError
from nexus.core.events import Event
from nexus.core.logging import get_logger
from nexus.ui.dialogs.settings_dialog import SettingsDialog
from nexus.ui.panels.ai_panel import AIPanel
from nexus.ui.panels.automation_panel import AutomationPanel
from nexus.ui.panels.calendar_panel import CalendarPanel
from nexus.ui.panels.dashboard_panel import DashboardPanel
from nexus.ui.panels.files_panel import FilesPanel
from nexus.ui.panels.notes_panel import NotesPanel
from nexus.ui.panels.tasks_panel import TasksPanel
from nexus.ui.shortcuts import SHORTCUTS, shortcuts_help_text
from nexus.ui.theme import ThemeManager

__all__ = ["MainWindow"]

_logger = get_logger("ui.main")


class _NotificationBridge(QObject):
    """Turns a bus notification (any thread) into a UI-thread signal."""

    message = Signal(str)


class MainWindow(QMainWindow):
    """The application shell hosting every module panel."""

    def __init__(
        self,
        context: AppContext,
        theme_manager: ThemeManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._ctx = context
        self._theme_manager = theme_manager
        self._docks: dict[str, QDockWidget] = {}
        self._panels: dict[str, QWidget] = {}
        self.setWindowTitle("Nexus")
        self.resize(1200, 800)

        self._dashboard = DashboardPanel(context)
        self._panels["dashboard"] = self._dashboard
        self.setCentralWidget(self._dashboard)

        self._build_docks()
        self._build_actions()
        self._build_menus()
        self._build_toolbar()

        self.statusBar().showMessage("Ready")
        self._bridge = _NotificationBridge()
        self._bridge.message.connect(self._show_notification)
        self._unsubscribe = self._ctx.events.subscribe(NOTIFICATION_TOPIC, self._on_notification)

    # -- construction -----------------------------------------------------

    def _build_docks(self) -> None:
        specs: list[tuple[str, str, QWidget]] = [
            ("notes", "Notes", NotesPanel(self._ctx)),
            ("tasks", "Tasks", TasksPanel(self._ctx)),
            ("calendar", "Calendar", CalendarPanel(self._ctx)),
            ("files", "Files", FilesPanel(self._ctx)),
            ("ai", "AI Assistant", AIPanel(self._ctx)),
            ("automation", "Automation", AutomationPanel(self._ctx)),
        ]
        previous: QDockWidget | None = None
        for key, title, panel in specs:
            dock = QDockWidget(title, self)
            dock.setObjectName(f"dock_{key}")
            dock.setWidget(panel)
            dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
            self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
            if previous is not None:
                self.tabifyDockWidget(previous, dock)
            self._docks[key] = dock
            self._panels[key] = panel
            previous = dock
        # Show the first tab (Notes) raised rather than the last-added one.
        if "notes" in self._docks:
            self._docks["notes"].raise_()

    def _build_actions(self) -> None:
        self._actions: dict[str, QAction] = {}
        handlers = {
            "focus_dashboard": lambda: self._focus_panel("dashboard"),
            "focus_notes": lambda: self._focus_panel("notes"),
            "focus_tasks": lambda: self._focus_panel("tasks"),
            "focus_files": lambda: self._focus_panel("files"),
            "focus_ai": lambda: self._focus_panel("ai"),
            "focus_calendar": lambda: self._focus_panel("calendar"),
            "focus_automation": lambda: self._focus_panel("automation"),
            "toggle_theme": self._on_toggle_theme,
            "settings": self._on_settings,
            "refresh": self._on_refresh,
            "quit": self.close,
        }
        for key, spec in SHORTCUTS.items():
            action = QAction(spec.label, self)
            action.setShortcut(QKeySequence(spec.key))
            handler = handlers.get(key)
            if handler is not None:
                action.triggered.connect(handler)
            self.addAction(action)  # window-level, so shortcuts work anywhere
            self._actions[key] = action

    def _build_menus(self) -> None:
        menubar = self.menuBar()

        file_menu = menubar.addMenu("&File")
        file_menu.addAction(self._actions["settings"])
        backup_action = QAction("Back up now", self)
        backup_action.triggered.connect(self._on_backup)
        file_menu.addAction(backup_action)
        file_menu.addSeparator()
        file_menu.addAction(self._actions["quit"])

        view_menu = menubar.addMenu("&View")
        view_menu.addAction(self._actions["focus_dashboard"])
        view_menu.addSeparator()
        for dock in self._docks.values():
            view_menu.addAction(dock.toggleViewAction())
        view_menu.addSeparator()
        view_menu.addAction(self._actions["toggle_theme"])
        view_menu.addAction(self._actions["refresh"])

        help_menu = menubar.addMenu("&Help")
        shortcuts_action = QAction("Keyboard shortcuts", self)
        shortcuts_action.triggered.connect(self._on_shortcuts_help)
        help_menu.addAction(shortcuts_action)
        about_action = QAction("About Nexus", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

    def _build_toolbar(self) -> None:
        toolbar = self.addToolBar("Main")
        toolbar.setObjectName("main_toolbar")
        toolbar.setMovable(False)
        for key in ("focus_dashboard", "focus_notes", "focus_tasks", "focus_ai"):
            toolbar.addAction(self._actions[key])
        toolbar.addSeparator()
        toolbar.addAction(self._actions["refresh"])
        toolbar.addAction(self._actions["toggle_theme"])

    # -- behaviour --------------------------------------------------------

    def _focus_panel(self, key: str) -> None:
        """Bring a panel forward: raise its dock (or focus the dashboard)."""
        dock = self._docks.get(key)
        if dock is None:  # the dashboard is the central widget
            self._dashboard.refresh()
            self._dashboard.setFocus()
            return
        dock.show()
        dock.raise_()
        dock.widget().setFocus()

    def _on_toggle_theme(self) -> None:
        theme = self._theme_manager.toggle()
        self.statusBar().showMessage(f"Theme: {theme}", 2000)

    def _on_settings(self) -> None:
        dialog = SettingsDialog(self._ctx, self._theme_manager, self)
        dialog.exec()

    def _on_refresh(self) -> None:
        for panel in self._panels.values():
            refresh = getattr(panel, "refresh", None)
            if callable(refresh):
                refresh()
        self.statusBar().showMessage("Refreshed", 1500)

    def _on_backup(self) -> None:
        try:
            path = self._ctx.database.backup()
        except NexusError as exc:
            QMessageBox.warning(self, "Nexus", str(exc))
            return
        self.statusBar().showMessage(f"Backed up to {path}", 4000)

    def _on_shortcuts_help(self) -> None:
        QMessageBox.information(self, "Keyboard shortcuts", shortcuts_help_text())

    def _on_about(self) -> None:
        QMessageBox.about(
            self,
            "About Nexus",
            "Nexus — a personal productivity and AI workspace.\n\n"
            "Notes, tasks, files, an AI assistant, automation, and a "
            "dashboard, all backed by a local encrypted database.",
        )

    # -- notifications ----------------------------------------------------

    def _on_notification(self, event: Event) -> None:
        """Bus handler (any thread): forward the message via the bridge."""
        message = str(event.payload.get("message", ""))
        if message:
            self._bridge.message.emit(message)

    def _show_notification(self, message: str) -> None:
        self.statusBar().showMessage(message, 5000)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt override name
        """Unsubscribe and release resources on window close."""
        try:
            self._unsubscribe()
        except Exception:  # pragma: no cover - defensive cleanup
            _logger.debug("notification unsubscribe failed", exc_info=True)
        super().closeEvent(event)

    def __enter__(self) -> MainWindow:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
