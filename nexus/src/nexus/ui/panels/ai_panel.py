"""AI Assistant panel: a chat client plus one-shot document tools.

Two tabs over :class:`~nexus.services.ai.AIService`:

* **Chat** keeps persistent sessions -- pick one, type, and the assistant's
  reply is stored and shown. History lives in the database, so sessions
  survive restarts.
* **Tools** runs the stateless document actions (summarise, explain code,
  rewrite, draft an email) on whatever text you paste in.

Calls run on the UI thread. That is fine for the default in-process "fake"
provider (instant, no network) which Nexus ships with; a real remote
provider would want a ``QThread`` worker so the window never blocks, and
:meth:`_run_blocking` is the single choke point where that would slot in.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from nexus.app_context import AppContext
from nexus.core.errors import NexusError
from nexus.core.logging import get_logger

__all__ = ["AIPanel"]

_logger = get_logger("ui.ai")

_T = TypeVar("_T")


class AIPanel(QWidget):
    """Chat sessions and one-shot document tools backed by AIForge."""

    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = context
        self._session_id: int | None = None
        self._build()
        self.reload_sessions()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._build_chat_tab(), "Chat")
        tabs.addTab(self._build_tools_tab(), "Tools")
        layout.addWidget(tabs)

    # -- chat -------------------------------------------------------------

    def _build_chat_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        top = QHBoxLayout()
        top.addWidget(QLabel("Session:"))
        self._session_combo = QComboBox()
        self._session_combo.currentIndexChanged.connect(self._on_session_changed)
        top.addWidget(self._session_combo, stretch=1)
        new_button = QPushButton("New")
        new_button.clicked.connect(self._on_new_session)
        top.addWidget(new_button)
        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(self._on_delete_session)
        top.addWidget(delete_button)
        layout.addLayout(top)

        self._transcript = QTextBrowser()
        self._transcript.setOpenExternalLinks(False)
        layout.addWidget(self._transcript, stretch=1)

        entry = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText("Message the assistant, then Enter")
        self._input.returnPressed.connect(self._on_send)
        entry.addWidget(self._input, stretch=1)
        send = QPushButton("Send")
        send.clicked.connect(self._on_send)
        entry.addWidget(send)
        layout.addLayout(entry)
        return tab

    def refresh(self) -> None:
        """Uniform refresh entry point (reloads sessions and transcript)."""
        self.reload_sessions()

    def reload_sessions(self) -> None:
        """Refresh the session list and show the first session's transcript."""
        self._session_combo.blockSignals(True)
        self._session_combo.clear()
        sessions = self._ctx.ai.list_sessions()
        for session in sessions:
            self._session_combo.addItem(session.title, session.id)
        self._session_combo.blockSignals(False)
        if sessions:
            self._session_id = sessions[0].id
            self._session_combo.setCurrentIndex(0)
            self._render_transcript()
        else:
            self._session_id = None
            self._transcript.setPlainText("Create a session to start chatting.")

    def _render_transcript(self) -> None:
        if self._session_id is None:
            self._transcript.clear()
            return
        try:
            session = self._ctx.ai.get_session(self._session_id)
        except NexusError as exc:
            self._transcript.setPlainText(str(exc))
            return
        lines = []
        for message in session.messages:
            who = "You" if message.role == "user" else "Assistant"
            lines.append(f"<p><b>{who}:</b> {_escape(message.content)}</p>")
        self._transcript.setHtml("".join(lines) or "<p><i>No messages yet. Say hello.</i></p>")
        self._transcript.verticalScrollBar().setValue(
            self._transcript.verticalScrollBar().maximum()
        )

    def _on_session_changed(self, _index: int) -> None:
        data = self._session_combo.currentData()
        self._session_id = int(data) if data is not None else None
        self._render_transcript()

    def _on_new_session(self) -> None:
        count = self._session_combo.count() + 1
        session = self._ctx.ai.create_session(title=f"Chat {count}")
        self.reload_sessions()
        index = self._session_combo.findData(session.id)
        if index >= 0:
            self._session_combo.setCurrentIndex(index)

    def _on_delete_session(self) -> None:
        if self._session_id is None:
            return
        self._ctx.ai.delete_session(self._session_id)
        self.reload_sessions()

    def _on_send(self) -> None:
        text = self._input.text().strip()
        if not text:
            return
        if self._session_id is None:
            self._on_new_session()
        session_id = self._session_id
        if session_id is None:  # creation failed
            return
        self._input.clear()
        result = self._run_blocking(lambda: self._ctx.ai.send_message(session_id, text))
        if result is not None:
            self._render_transcript()

    # -- tools ------------------------------------------------------------

    def _build_tools_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        layout.addWidget(QLabel("Input"))
        self._tools_input = QPlainTextEdit()
        self._tools_input.setPlaceholderText("Paste text or code here…")
        layout.addWidget(self._tools_input, stretch=1)

        buttons = QHBoxLayout()
        for label, handler in (
            ("Summarise", self._on_summarize),
            ("Explain code", self._on_explain),
            ("Rewrite", self._on_rewrite),
            ("Draft email", self._on_email),
        ):
            button = QPushButton(label)
            button.clicked.connect(handler)
            buttons.addWidget(button)
        layout.addLayout(buttons)

        layout.addWidget(QLabel("Output"))
        self._tools_output = QPlainTextEdit()
        self._tools_output.setReadOnly(True)
        layout.addWidget(self._tools_output, stretch=1)
        return tab

    def _tools_text(self) -> str | None:
        text = self._tools_input.toPlainText().strip()
        if not text:
            QMessageBox.information(self, "Nexus", "Enter some text first.")
            return None
        return text

    def _on_summarize(self) -> None:
        text = self._tools_text()
        if text is not None:
            self._show_tool_result(lambda: self._ctx.ai.summarize(text))

    def _on_explain(self) -> None:
        text = self._tools_text()
        if text is not None:
            self._show_tool_result(lambda: self._ctx.ai.explain_code(text))

    def _on_rewrite(self) -> None:
        text = self._tools_text()
        if text is not None:
            self._show_tool_result(lambda: self._ctx.ai.rewrite(text))

    def _on_email(self) -> None:
        text = self._tools_text()
        if text is not None:
            self._show_tool_result(lambda: self._ctx.ai.generate_email(text))

    def _show_tool_result(self, action: Callable[[], str]) -> None:
        result = self._run_blocking(action)
        if result is not None:
            self._tools_output.setPlainText(result)

    # -- shared -----------------------------------------------------------

    def _run_blocking(self, action: Callable[[], _T]) -> _T | None:
        """Run *action*, showing a wait cursor and surfacing errors as dialogs.

        This is the single point where every AI call passes through, so a
        future background-worker implementation only has to change here.
        """
        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            return action()
        except NexusError as exc:
            QMessageBox.warning(self, "Nexus", str(exc))
            return None
        finally:
            QGuiApplication.restoreOverrideCursor()


def _escape(text: str) -> str:
    """Escape HTML special characters and preserve line breaks for display."""
    escaped = (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
    )
    return escaped
