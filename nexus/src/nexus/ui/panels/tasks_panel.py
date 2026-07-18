"""Tasks panel: a kanban board with drag-and-drop between columns.

Each status column is a :class:`_ColumnList` (a ``QListWidget`` in
InternalMove-ish drag mode). Dropping a card calls
``TasksService.move(...)`` with the destination column and row, so the
service -- already unit-tested -- owns the ordering logic and the board just
reflects it. After any drop the board reloads from the service, keeping the
view and the persisted state in lockstep.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from nexus.app_context import AppContext
from nexus.core.logging import get_logger

__all__ = ["TasksPanel"]

_logger = get_logger("ui.tasks")

_COLUMNS = ("todo", "doing", "done")
_TASK_ROLE = Qt.ItemDataRole.UserRole


class _ColumnList(QListWidget):
    """A kanban column; emits :attr:`dropped` after a card is dropped in."""

    dropped = Signal(int, str, int)  # task_id, destination status, row

    def __init__(self, status: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._status = status
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

    def dropEvent(self, event: object) -> None:  # noqa: N802 - Qt override name
        source = event.source() if hasattr(event, "source") else None
        item = source.currentItem() if isinstance(source, QListWidget) else None
        task_id = int(item.data(_TASK_ROLE)) if item is not None else None
        row = self.indexAt(event.position().toPoint()).row()  # type: ignore[attr-defined]
        if row < 0:
            row = self.count()
        if task_id is not None:
            self.dropped.emit(task_id, self._status, row)
        event.acceptProposedAction()  # type: ignore[attr-defined]


class TasksPanel(QWidget):
    """A kanban board over the currently selected project."""

    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = context
        self._project_id: int | None = None
        self._columns: dict[str, _ColumnList] = {}
        self._build()
        self.reload_projects()

    def _build(self) -> None:
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        self._project_combo = QComboBox()
        self._project_combo.currentIndexChanged.connect(self._on_project_changed)
        top.addWidget(QLabel("Project:"))
        top.addWidget(self._project_combo, stretch=1)
        new_project = QPushButton("New project")
        new_project.clicked.connect(self._on_new_project)
        top.addWidget(new_project)
        layout.addLayout(top)

        add_row = QHBoxLayout()
        self._new_task = QLineEdit()
        self._new_task.setPlaceholderText("New task title, then Enter")
        self._new_task.returnPressed.connect(self._on_add_task)
        add_row.addWidget(self._new_task, stretch=1)
        layout.addLayout(add_row)

        board = QHBoxLayout()
        for status in _COLUMNS:
            column_widget = QWidget()
            column_layout = QVBoxLayout(column_widget)
            column_layout.setContentsMargins(2, 2, 2, 2)
            column_layout.addWidget(QLabel(status.upper()))
            column = _ColumnList(status)
            column.dropped.connect(self._on_dropped)
            column.itemDoubleClicked.connect(self._on_complete)
            self._columns[status] = column
            column_layout.addWidget(column)
            board.addWidget(column_widget)
        layout.addLayout(board, stretch=1)

        self._hint = QLabel("Drag cards between columns. Double-click to complete.")
        layout.addWidget(self._hint)

    def reload_projects(self) -> None:
        """Refresh the project list; select the first project if any."""
        self._project_combo.blockSignals(True)
        self._project_combo.clear()
        projects = self._ctx.tasks.list_projects()
        for project in projects:
            self._project_combo.addItem(project.name, project.id)
        self._project_combo.blockSignals(False)
        if projects:
            self._project_id = projects[0].id
            self._project_combo.setCurrentIndex(0)
            self.refresh()
        else:
            self._project_id = None
            self._clear_board()

    def refresh(self) -> None:
        """Reload the board for the current project from the service."""
        self._clear_board()
        if self._project_id is None:
            return
        board = self._ctx.tasks.board(self._project_id)
        for status, column in self._columns.items():
            for task in board.get(status, []):
                item = QListWidgetItem(task.title)
                item.setData(_TASK_ROLE, task.id)
                column.addItem(item)

    def _clear_board(self) -> None:
        for column in self._columns.values():
            column.clear()

    def _on_project_changed(self, _index: int) -> None:
        data = self._project_combo.currentData()
        self._project_id = int(data) if data is not None else None
        self.refresh()

    def _on_new_project(self) -> None:
        name, ok = QInputDialog.getText(self, "New project", "Project name:")
        if ok and name.strip():
            self._ctx.tasks.create_project(name.strip())
            self.reload_projects()

    def _on_add_task(self) -> None:
        title = self._new_task.text().strip()
        if not title or self._project_id is None:
            return
        self._ctx.tasks.add_task(self._project_id, title)
        self._new_task.clear()
        self.refresh()

    def _on_dropped(self, task_id: int, status: str, row: int) -> None:
        self._ctx.tasks.move(task_id, status=status, position=row)
        self.refresh()

    def _on_complete(self, item: QListWidgetItem) -> None:
        task_id = int(item.data(_TASK_ROLE))
        self._ctx.tasks.complete(task_id)
        self.refresh()
