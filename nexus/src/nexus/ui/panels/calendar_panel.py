"""Calendar panel: a month view of tasks by due date.

Wraps a ``QCalendarWidget``. Whenever the visible month changes, the panel
asks :class:`~nexus.services.tasks.TasksService` for the tasks due in that
range, highlights the days that have any, and -- when a day is selected --
lists the tasks due that day. Dates are handled in UTC to match how due
dates are stored, so highlighting and the day list always agree.
"""

from __future__ import annotations

import datetime as dt

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QTextCharFormat
from PySide6.QtWidgets import (
    QCalendarWidget,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from nexus.app_context import AppContext
from nexus.core.logging import get_logger
from nexus.services.tasks import TaskDTO

__all__ = ["CalendarPanel"]

_logger = get_logger("ui.calendar")


def _qdate_to_date(qdate: QDate) -> dt.date:
    return dt.date(qdate.year(), qdate.month(), qdate.day())


def _month_bounds(year: int, month: int) -> tuple[dt.datetime, dt.datetime]:
    """Return aware-UTC [start, end) datetimes spanning the whole month."""
    start = dt.datetime(year, month, 1, tzinfo=dt.UTC)
    end_year, end_month = (year + 1, 1) if month == 12 else (year, month + 1)
    end = dt.datetime(end_year, end_month, 1, tzinfo=dt.UTC)
    return start, end


class CalendarPanel(QWidget):
    """A month calendar that highlights and lists tasks by due date."""

    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = context
        self._by_day: dict[dt.date, list[TaskDTO]] = {}
        self._highlighted: list[QDate] = []
        self._build()
        today = QDate.currentDate()
        self._reload_month(today.year(), today.month())
        self._on_selection_changed()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        self._calendar = QCalendarWidget()
        self._calendar.setGridVisible(True)
        self._calendar.currentPageChanged.connect(self._reload_month)
        self._calendar.selectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._calendar)

        self._day_label = QLabel("")
        day_font = self._day_label.font()
        day_font.setBold(True)
        self._day_label.setFont(day_font)
        layout.addWidget(self._day_label)

        self._day_list = QListWidget()
        layout.addWidget(self._day_list, stretch=1)

    def refresh(self) -> None:
        """Reload the currently visible month (e.g. after tasks change)."""
        self._reload_month(self._calendar.yearShown(), self._calendar.monthShown())
        self._on_selection_changed()

    def _reload_month(self, year: int, month: int) -> None:
        start, end = _month_bounds(year, month)
        tasks = self._ctx.tasks.calendar(start, end)
        self._by_day = {}
        for task in tasks:
            due = task.due_at
            if due is None:
                continue
            day = due.astimezone(dt.UTC).date()
            self._by_day.setdefault(day, []).append(task)
        self._apply_highlights()

    def _apply_highlights(self) -> None:
        plain = QTextCharFormat()
        for qdate in self._highlighted:
            self._calendar.setDateTextFormat(qdate, plain)
        self._highlighted = []
        highlight = QTextCharFormat()
        highlight.setFontWeight(75)  # bold
        highlight.setForeground(Qt.GlobalColor.cyan)
        for day in self._by_day:
            qdate = QDate(day.year, day.month, day.day)
            self._calendar.setDateTextFormat(qdate, highlight)
            self._highlighted.append(qdate)

    def _on_selection_changed(self) -> None:
        selected = _qdate_to_date(self._calendar.selectedDate())
        self._day_label.setText(selected.strftime("%A, %d %B %Y"))
        self._day_list.clear()
        tasks = self._by_day.get(selected, [])
        if not tasks:
            self._day_list.addItem(QListWidgetItem("No tasks due."))
            return
        for task in tasks:
            done = "✓ " if task.is_done else ""
            self._day_list.addItem(QListWidgetItem(f"{done}{task.title}"))
