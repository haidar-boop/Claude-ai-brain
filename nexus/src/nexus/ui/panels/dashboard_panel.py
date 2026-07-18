"""Dashboard panel: headline stats, storage, productivity, and activity.

A read-only overview built from :class:`~nexus.services.dashboard.DashboardService`.
It refreshes on demand (a button), whenever the panel is shown, and on a
gentle timer so the numbers stay current while it is visible. Every value
comes from the service's detached DTOs -- the panel only lays them out.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from nexus.app_context import AppContext
from nexus.core.logging import get_logger

__all__ = ["DashboardPanel"]

_logger = get_logger("ui.dashboard")

_REFRESH_MS = 5000


def _format_size(size_bytes: int) -> str:
    value = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


class _StatCard(QFrame):
    """A small framed number-and-caption tile."""

    def __init__(self, caption: str) -> None:
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(self)
        self._value = QLabel("0")
        font = self._value.font()
        font.setPointSize(font.pointSize() + 8)
        font.setBold(True)
        self._value.setFont(font)
        layout.addWidget(self._value)
        layout.addWidget(QLabel(caption))

    def set_value(self, value: int) -> None:
        self._value.setText(str(value))


class DashboardPanel(QWidget):
    """An at-a-glance overview of everything in the workspace."""

    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = context
        self._cards: dict[str, _StatCard] = {}
        self._build()
        self._timer = QTimer(self)
        self._timer.setInterval(_REFRESH_MS)
        self._timer.timeout.connect(self.refresh)
        self.refresh()

    def _build(self) -> None:
        layout = QVBoxLayout(self)

        header = QHBoxLayout()
        title = QLabel("Workspace overview")
        title_font = title.font()
        title_font.setBold(True)
        title.setFont(title_font)
        header.addWidget(title)
        header.addStretch(1)
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh)
        header.addWidget(refresh_button)
        layout.addLayout(header)

        cards = QGridLayout()
        captions = [
            ("notes", "Notes"),
            ("tasks", "Tasks"),
            ("open_tasks", "Open"),
            ("completed_tasks", "Completed"),
            ("files", "Indexed files"),
            ("chat_sessions", "Chats"),
        ]
        for index, (key, caption) in enumerate(captions):
            card = _StatCard(caption)
            self._cards[key] = card
            cards.addWidget(card, index // 3, index % 3)
        layout.addLayout(cards)

        lower = QHBoxLayout()

        storage_box = QGroupBox("Storage")
        self._storage_form = QFormLayout(storage_box)
        self._db_size = QLabel("—")
        self._file_size = QLabel("—")
        self._total_size = QLabel("—")
        self._storage_form.addRow("Database:", self._db_size)
        self._storage_form.addRow("Indexed files:", self._file_size)
        self._storage_form.addRow("Total:", self._total_size)
        lower.addWidget(storage_box)

        productivity_box = QGroupBox("Completed tasks (last 7 days)")
        self._productivity_layout = QFormLayout(productivity_box)
        lower.addWidget(productivity_box, stretch=1)
        layout.addLayout(lower)

        activity_box = QGroupBox("Recent activity")
        activity_layout = QVBoxLayout(activity_box)
        self._activity = QLabel("No activity yet.")
        self._activity.setWordWrap(True)
        self._activity.setTextFormat(Qt.TextFormat.RichText)
        activity_layout.addWidget(self._activity)
        layout.addWidget(activity_box, stretch=1)

    def showEvent(self, event: object) -> None:  # noqa: N802 - Qt override name
        self.refresh()
        self._timer.start()
        super().showEvent(event)  # type: ignore[arg-type]

    def hideEvent(self, event: object) -> None:  # noqa: N802 - Qt override name
        self._timer.stop()
        super().hideEvent(event)  # type: ignore[arg-type]

    def refresh(self) -> None:
        """Reload every metric from the dashboard service."""
        stats = self._ctx.dashboard.stats()
        self._cards["notes"].set_value(stats.notes)
        self._cards["tasks"].set_value(stats.tasks)
        self._cards["open_tasks"].set_value(stats.open_tasks)
        self._cards["completed_tasks"].set_value(stats.completed_tasks)
        self._cards["files"].set_value(stats.files)
        self._cards["chat_sessions"].set_value(stats.chat_sessions)

        usage = self._ctx.dashboard.storage_usage()
        self._db_size.setText(_format_size(usage.database_bytes))
        self._file_size.setText(_format_size(usage.indexed_file_bytes))
        self._total_size.setText(_format_size(usage.total_bytes))

        self._render_productivity()
        self._render_activity()

    def _render_productivity(self) -> None:
        while self._productivity_layout.rowCount():
            self._productivity_layout.removeRow(0)
        metrics = self._ctx.dashboard.productivity(days=7)
        peak = max(metrics.completed_per_day.values(), default=0)
        for day, count in metrics.completed_per_day.items():
            bar = QProgressBar()
            bar.setMaximum(max(peak, 1))
            bar.setValue(count)
            bar.setFormat(str(count))
            self._productivity_layout.addRow(day[5:], bar)  # MM-DD

    def _render_activity(self) -> None:
        items = self._ctx.dashboard.recent_activity(limit=12)
        if not items:
            self._activity.setText("No activity yet.")
            return
        rows = [f"<b>{_escape(item.topic)}</b> — {_escape(str(item.detail))}" for item in items]
        self._activity.setText("<br>".join(rows))


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
