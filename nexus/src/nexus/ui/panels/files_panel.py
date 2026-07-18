"""Files panel: index folders, full-text search, preview, and de-duplicate.

The panel is a thin view over :class:`~nexus.services.files.FilesService`:
it indexes what the user points it at, runs FTS5 searches, shows a preview
of the selected file, and can scan the index for duplicate content. All the
work -- hashing, extraction, ranking -- lives in the service and is unit
tested there; here we only gather input and render the returned DTOs.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
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
from nexus.core.errors import NexusError
from nexus.core.logging import get_logger
from nexus.services.files import FileDTO

__all__ = ["FilesPanel"]

_logger = get_logger("ui.files")

_PATH_ROLE = Qt.ItemDataRole.UserRole
_ID_ROLE = Qt.ItemDataRole.UserRole + 1


def _format_size(size_bytes: int) -> str:
    """Render a byte count as a short human-readable string."""
    value = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


class FilesPanel(QWidget):
    """Index files, search them, preview content, and find duplicates."""

    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = context
        self._build()
        self.refresh()

    def _build(self) -> None:
        layout = QVBoxLayout(self)

        toolbar = QHBoxLayout()
        index_folder = QPushButton("Index folder…")
        index_folder.clicked.connect(self._on_index_folder)
        toolbar.addWidget(index_folder)
        index_file = QPushButton("Index file…")
        index_file.clicked.connect(self._on_index_file)
        toolbar.addWidget(index_file)
        duplicates = QPushButton("Find duplicates")
        duplicates.clicked.connect(self._on_find_duplicates)
        toolbar.addWidget(duplicates)
        toolbar.addStretch(1)
        remove = QPushButton("Remove from index")
        remove.clicked.connect(self._on_remove)
        toolbar.addWidget(remove)
        layout.addLayout(toolbar)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search indexed files (full text)…")
        self._search.textChanged.connect(self._on_search)
        layout.addWidget(self._search)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, stretch=1)

        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.currentItemChanged.connect(self._on_select)
        splitter.addWidget(self._list)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self._preview_header = QLabel("Select a file to preview")
        self._preview_header.setWordWrap(True)
        right_layout.addWidget(self._preview_header)
        self._preview = QPlainTextEdit()
        self._preview.setReadOnly(True)
        right_layout.addWidget(self._preview, stretch=1)
        splitter.addWidget(right)
        splitter.setSizes([320, 480])

        self._status = QLabel("")
        layout.addWidget(self._status)

    def refresh(self) -> None:
        """Show recent search results, or a hint when the query is empty."""
        query = self._search.text().strip()
        if query:
            self._populate(self._ctx.files.search(query))
        else:
            self._list.clear()
            self._status.setText("Index a folder, then search its contents.")

    def _populate(self, files: list[FileDTO]) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        for dto in files:
            item = QListWidgetItem(f"{dto.name}  —  {_format_size(dto.size_bytes)}")
            item.setData(_PATH_ROLE, dto.path)
            item.setData(_ID_ROLE, dto.id)
            item.setToolTip(dto.path)
            self._list.addItem(item)
        self._list.blockSignals(False)
        self._status.setText(f"{len(files)} file(s)")

    def _on_search(self, _text: str) -> None:
        self.refresh()

    def _on_index_folder(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Index folder")
        if not directory:
            return
        try:
            indexed = self._ctx.files.index_directory(directory, compute_hash=True)
        except NexusError as exc:
            QMessageBox.warning(self, "Nexus", str(exc))
            return
        self._status.setText(f"Indexed {len(indexed)} file(s) from {directory}")
        self.refresh()

    def _on_index_file(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(self, "Index file")
        if not path:
            return
        try:
            self._ctx.files.index_file(path, compute_hash=True)
        except NexusError as exc:
            QMessageBox.warning(self, "Nexus", str(exc))
            return
        self._status.setText(f"Indexed {Path(path).name}")
        self.refresh()

    def _on_select(self, current: QListWidgetItem | None, _previous: object = None) -> None:
        if current is None:
            self._preview_header.setText("Select a file to preview")
            self._preview.clear()
            return
        path = str(current.data(_PATH_ROLE))
        try:
            preview = self._ctx.files.preview(path)
        except NexusError as exc:
            self._preview_header.setText(str(exc))
            self._preview.clear()
            return
        mime = preview.mime_type or "unknown type"
        self._preview_header.setText(
            f"{preview.name}\n{preview.path}\n{_format_size(preview.size_bytes)} · {mime}"
        )
        self._preview.setPlainText(preview.snippet or "(no text preview available)")

    def _on_remove(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        file_id = int(item.data(_ID_ROLE))
        try:
            self._ctx.files.remove(file_id)
        except NexusError as exc:
            QMessageBox.warning(self, "Nexus", str(exc))
            return
        self.refresh()

    def _on_find_duplicates(self) -> None:
        groups = self._ctx.files.find_duplicates()
        if not groups:
            QMessageBox.information(self, "Nexus", "No duplicate files found in the index.")
            return
        self._list.blockSignals(True)
        self._list.clear()
        total = 0
        for group in groups:
            header = QListWidgetItem(
                f"— {len(group.files)} copies · {_format_size(group.size_bytes)} each —"
            )
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            self._list.addItem(header)
            for dto in group.files:
                total += 1
                item = QListWidgetItem(f"    {dto.name}")
                item.setData(_PATH_ROLE, dto.path)
                item.setData(_ID_ROLE, dto.id)
                item.setToolTip(dto.path)
                self._list.addItem(item)
        self._list.blockSignals(False)
        self._status.setText(f"{len(groups)} duplicate group(s), {total} file(s)")
