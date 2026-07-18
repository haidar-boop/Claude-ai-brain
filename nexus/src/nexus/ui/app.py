"""Launch the Nexus desktop application.

:func:`run` is the single GUI entry point: it builds the ``QApplication``,
stands up an :class:`~nexus.app_context.AppContext` (opening the database and
wiring every service), restores the saved theme, shows the main window, and
runs the event loop -- disposing the context cleanly on exit. ``python -m
nexus`` calls straight through to here.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from nexus.app_context import AppContext
from nexus.core.logging import get_logger
from nexus.ui.dialogs.settings_dialog import SETTINGS_APP, SETTINGS_ORG
from nexus.ui.main_window import MainWindow
from nexus.ui.theme import ThemeManager

__all__ = ["run"]

_logger = get_logger("ui.app")


def run(
    *,
    data_dir: Path | str | None = None,
    config_path: Path | str | None = None,
    argv: list[str] | None = None,
) -> int:
    """Build the app, show the main window, and run the Qt event loop.

    Returns the process exit code. *data_dir* and *config_path* override where
    Nexus stores data and reads configuration, mirroring
    :meth:`AppContext.create`.
    """
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(SETTINGS_APP)
    app.setOrganizationName(SETTINGS_ORG)

    context = AppContext.create(data_dir=data_dir, config_path=config_path)
    try:
        settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        theme = str(settings.value("theme", context.config.ui.theme))
        theme_manager = ThemeManager(app, initial=theme)

        window = MainWindow(context, theme_manager)
        window.show()
        _logger.info("nexus started")
        return app.exec()
    finally:
        context.close()


if __name__ == "__main__":  # pragma: no cover - manual launch
    raise SystemExit(run())
