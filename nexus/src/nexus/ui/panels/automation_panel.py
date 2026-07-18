"""Automation panel: view, toggle, create, and delete workflow rules.

A rule is a trigger (an event topic), optional conditions, and actions to run
when it fires. This panel manages the stored rules through
:class:`~nexus.services.automation.AutomationService` and, after any change,
calls :meth:`AppContext.reload_automation` so the live engine matches what is
persisted -- toggling a rule off actually stops it firing, immediately.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from nexus.app_context import AppContext
from nexus.automation.rules import ActionSpec
from nexus.core.errors import NexusError
from nexus.core.logging import get_logger

__all__ = ["AutomationPanel"]

_logger = get_logger("ui.automation")

_ID_ROLE = Qt.ItemDataRole.UserRole

# Event topics the services publish, offered as trigger suggestions. The combo
# is editable, so any topic can be typed -- these are just the common ones.
_TRIGGERS = (
    "note.created",
    "note.updated",
    "note.deleted",
    "task.created",
    "task.completed",
    "task.moved",
    "file.indexed",
    "file.removed",
    "fs.created",
    "fs.modified",
    "fs.deleted",
    "chat.session_created",
)

_ACTIONS = ("notify", "log", "noop")


class _NewRuleDialog(QDialog):
    """Collect the fields for a new rule: name, trigger, action, message."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New automation rule")
        form = QFormLayout(self)

        self._name = QLineEdit()
        form.addRow("Name:", self._name)

        self._trigger = QComboBox()
        self._trigger.setEditable(True)
        self._trigger.addItems(_TRIGGERS)
        form.addRow("When (event):", self._trigger)

        self._action = QComboBox()
        self._action.addItems(_ACTIONS)
        form.addRow("Do:", self._action)

        self._message = QLineEdit()
        self._message.setPlaceholderText("Notification / log message (optional)")
        form.addRow("Message:", self._message)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def values(self) -> tuple[str, str, ActionSpec]:
        """Return the entered (name, trigger, action-spec)."""
        name = self._name.text().strip()
        trigger = self._trigger.currentText().strip()
        action_type = self._action.currentText().strip()
        message = self._message.text().strip()
        params = {"message": message} if message else {}
        return name, trigger, ActionSpec(type=action_type, params=params)


class AutomationPanel(QWidget):
    """List workflow rules and let the user create, toggle, and remove them."""

    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = context
        self._suspend_item_signal = False
        self._build()
        self.refresh()

    def _build(self) -> None:
        layout = QVBoxLayout(self)

        header = QHBoxLayout()
        header.addWidget(QLabel("Workflow rules (tick to enable):"))
        header.addStretch(1)
        new_button = QPushButton("New rule…")
        new_button.clicked.connect(self._on_new_rule)
        header.addWidget(new_button)
        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(self._on_delete)
        header.addWidget(delete_button)
        layout.addLayout(header)

        self._list = QListWidget()
        self._list.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self._list, stretch=1)

        self._status = QLabel("")
        layout.addWidget(self._status)

    def refresh(self) -> None:
        """Reload the rule list from the service."""
        self._suspend_item_signal = True
        self._list.clear()
        rules = self._ctx.automation.list_rules()
        for rule in rules:
            actions = ", ".join(spec.type for spec in rule.actions) or "—"
            item = QListWidgetItem(f"{rule.name}   ·   on {rule.trigger}   ·   {actions}")
            item.setData(_ID_ROLE, rule.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if rule.enabled else Qt.CheckState.Unchecked)
            self._list.addItem(item)
        self._suspend_item_signal = False
        enabled = sum(1 for r in rules if r.enabled)
        self._status.setText(f"{len(rules)} rule(s), {enabled} enabled")

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        if self._suspend_item_signal:
            return
        rule_id = int(item.data(_ID_ROLE))
        enabled = item.checkState() == Qt.CheckState.Checked
        try:
            self._ctx.automation.set_enabled(rule_id, enabled)
        except NexusError as exc:
            QMessageBox.warning(self, "Nexus", str(exc))
        self._ctx.reload_automation()
        self.refresh()

    def _on_new_rule(self) -> None:
        dialog = _NewRuleDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, trigger, action = dialog.values()
        if not name or not trigger:
            QMessageBox.information(self, "Nexus", "A rule needs a name and a trigger event.")
            return
        try:
            self._ctx.automation.create_rule(name, trigger, actions=[action])
        except NexusError as exc:
            QMessageBox.warning(self, "Nexus", str(exc))
            return
        self._ctx.reload_automation()
        self.refresh()

    def _on_delete(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        rule_id = int(item.data(_ID_ROLE))
        try:
            self._ctx.automation.delete_rule(rule_id)
        except NexusError as exc:
            QMessageBox.warning(self, "Nexus", str(exc))
            return
        self._ctx.reload_automation()
        self.refresh()
