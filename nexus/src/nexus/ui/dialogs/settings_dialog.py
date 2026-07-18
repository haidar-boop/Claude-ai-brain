"""The settings dialog: appearance plus read-only environment details.

Appearance (the theme) is a pure UI preference, so it is applied live through
the :class:`~nexus.ui.theme.ThemeManager` and remembered in ``QSettings`` --
no database or config-file round-trip needed. AI and storage details are
shown read-only with a pointer to ``config.yaml``, which is the single source
of truth for anything that affects the backend (provider, model, paths), so
the GUI never quietly disagrees with the file the CLI and API also read.
"""

from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from nexus.app_context import AppContext
from nexus.core.logging import get_logger
from nexus.ui.theme import ThemeManager, available_themes

__all__ = ["SETTINGS_APP", "SETTINGS_ORG", "SettingsDialog"]

_logger = get_logger("ui.settings")

SETTINGS_ORG = "Nexus"
SETTINGS_APP = "NexusWorkspace"


class SettingsDialog(QDialog):
    """Edit the theme; review AI and storage configuration."""

    def __init__(
        self,
        context: AppContext,
        theme_manager: ThemeManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._ctx = context
        self._theme_manager = theme_manager
        self._initial_theme = theme_manager.current
        self.setWindowTitle("Settings")
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)

        appearance = QGroupBox("Appearance")
        appearance_form = QFormLayout(appearance)
        self._theme = QComboBox()
        self._theme.addItems(available_themes())
        self._theme.setCurrentText(self._theme_manager.current)
        self._theme.currentTextChanged.connect(self._theme_manager.apply)
        appearance_form.addRow("Theme:", self._theme)
        layout.addWidget(appearance)

        ai = QGroupBox("AI (edit config.yaml to change)")
        ai_form = QFormLayout(ai)
        ai_form.addRow("Provider:", QLabel(self._ctx.config.ai.default_provider))
        ai_form.addRow("Model:", QLabel(self._ctx.config.ai.default_model or "(provider default)"))
        layout.addWidget(ai)

        storage = QGroupBox("Storage")
        storage_form = QFormLayout(storage)
        db_label = QLabel(str(self._ctx.paths.database))
        db_label.setWordWrap(True)
        storage_form.addRow("Database:", db_label)
        backups_label = QLabel(str(self._ctx.paths.backups))
        backups_label.setWordWrap(True)
        storage_form.addRow("Backups:", backups_label)
        layout.addWidget(storage)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self._on_reject)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        settings.setValue("theme", self._theme.currentText())
        self.accept()

    def _on_reject(self) -> None:
        # Restore the theme that was active when the dialog opened, since we
        # applied changes live for preview.
        self._theme_manager.apply(self._initial_theme)
        self.reject()
