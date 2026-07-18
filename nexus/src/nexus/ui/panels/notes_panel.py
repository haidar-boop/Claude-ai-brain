"""Notes panel: a searchable list of notes beside a markdown editor."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from nexus.app_context import AppContext
from nexus.core.logging import get_logger

__all__ = ["NotesPanel"]

_logger = get_logger("ui.notes")


class NotesPanel(QWidget):
    """List, create, edit, and search markdown notes."""

    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = context
        self._current_id: int | None = None
        self._build()
        self.refresh()

    def _build(self) -> None:
        layout = QVBoxLayout(self)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search notes...")
        self._search.textChanged.connect(self._on_search)
        layout.addWidget(self._search)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, stretch=1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self._list = QListWidget()
        self._list.currentItemChanged.connect(self._on_select)
        left_layout.addWidget(self._list)
        new_button = QPushButton("New note")
        new_button.clicked.connect(self._on_new)
        left_layout.addWidget(new_button)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self._title = QLineEdit()
        self._title.setPlaceholderText("Title")
        right_layout.addWidget(self._title)
        self._tags = QLineEdit()
        self._tags.setPlaceholderText("tags, comma, separated")
        right_layout.addWidget(self._tags)
        self._body = QPlainTextEdit()
        self._body.setPlaceholderText("Write markdown here. Use [[wiki links]] to link notes.")
        right_layout.addWidget(self._body, stretch=1)

        buttons = QHBoxLayout()
        self._save_button = QPushButton("Save")
        self._save_button.clicked.connect(self._on_save)
        buttons.addWidget(self._save_button)
        self._delete_button = QPushButton("Delete")
        self._delete_button.clicked.connect(self._on_delete)
        buttons.addWidget(self._delete_button)
        self._links = QLabel("")
        buttons.addWidget(self._links, stretch=1)
        right_layout.addLayout(buttons)
        splitter.addWidget(right)
        splitter.setSizes([250, 550])

    def refresh(self, *, query: str = "") -> None:
        """Reload the note list, preserving selection where possible."""
        self._list.blockSignals(True)
        self._list.clear()
        notes = self._ctx.notes.search(query) if query else self._ctx.notes.list_notes()
        for note in notes:
            item = QListWidgetItem(note.title)
            item.setData(Qt.ItemDataRole.UserRole, note.id)
            self._list.addItem(item)
        self._list.blockSignals(False)

    def _on_search(self, text: str) -> None:
        self.refresh(query=text.strip())

    def _on_new(self) -> None:
        self._current_id = None
        self._title.clear()
        self._tags.clear()
        self._body.clear()
        self._links.clear()
        self._title.setFocus()

    def _on_select(self, current: QListWidgetItem | None, _previous: object = None) -> None:
        if current is None:
            return
        note_id = int(current.data(Qt.ItemDataRole.UserRole))
        note = self._ctx.notes.get(note_id)
        self._current_id = note.id
        self._title.setText(note.title)
        self._tags.setText(", ".join(note.tags))
        self._body.setPlainText(note.body)
        self._links.setText(f"Links: {', '.join(note.links)}" if note.links else "")

    def _on_save(self) -> None:
        title = self._title.text().strip()
        if not title:
            QMessageBox.warning(self, "Nexus", "A note needs a title.")
            return
        tags = [t.strip() for t in self._tags.text().split(",") if t.strip()]
        body = self._body.toPlainText()
        if self._current_id is None:
            note = self._ctx.notes.create(title, body, tags=tags)
            self._current_id = note.id
        else:
            self._ctx.notes.update(self._current_id, title=title, body=body, tags=tags)
        self.refresh(query=self._search.text().strip())

    def _on_delete(self) -> None:
        if self._current_id is None:
            return
        self._ctx.notes.delete(self._current_id)
        self._on_new()
        self.refresh()
