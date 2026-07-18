"""Widget tests for the module panels, run offscreen.

Each panel is driven the way the UI drives it -- setting inputs and invoking
the same slots the buttons and signals call -- and then checked against the
service state it should have produced. Modal dialogs are patched out so error
paths and confirmations never block a headless run.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

from nexus.automation.rules import ActionSpec
from nexus.ui.panels.ai_panel import AIPanel
from nexus.ui.panels.automation_panel import AutomationPanel
from nexus.ui.panels.calendar_panel import CalendarPanel
from nexus.ui.panels.dashboard_panel import DashboardPanel
from nexus.ui.panels.files_panel import FilesPanel
from nexus.ui.panels.notes_panel import NotesPanel
from nexus.ui.panels.tasks_panel import TasksPanel


@pytest.fixture(autouse=True)
def _no_modal_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace blocking message boxes with no-ops so tests never hang."""
    ok = QMessageBox.StandardButton.Ok
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: ok)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: ok)
    monkeypatch.setattr(QMessageBox, "about", lambda *a, **k: None)


# -- notes -----------------------------------------------------------------


def test_notes_panel_create_and_search(qtbot: QtBot, app_ctx: Any) -> None:
    panel = NotesPanel(app_ctx)
    qtbot.addWidget(panel)
    assert panel._list.count() == 0

    panel._title.setText("Shopping")
    panel._body.setPlainText("Milk and [[Bread]]")
    panel._tags.setText("home, errands")
    panel._on_save()

    assert panel._list.count() == 1
    stored = app_ctx.notes.list_notes()
    assert stored[0].title == "Shopping"
    assert set(stored[0].tags) == {"home", "errands"}

    app_ctx.notes.create("Work note")
    panel.refresh()
    assert panel._list.count() == 2
    panel._search.setText("Shopping")
    assert panel._list.count() == 1


def test_notes_panel_delete(qtbot: QtBot, app_ctx: Any) -> None:
    note = app_ctx.notes.create("Temp")
    panel = NotesPanel(app_ctx)
    qtbot.addWidget(panel)
    panel._current_id = note.id
    panel._on_delete()
    assert app_ctx.notes.list_notes() == []


# -- tasks -----------------------------------------------------------------


def test_tasks_panel_add_and_move(qtbot: QtBot, app_ctx: Any) -> None:
    app_ctx.tasks.create_project("Board")
    panel = TasksPanel(app_ctx)
    qtbot.addWidget(panel)
    assert panel._project_id is not None

    panel._new_task.setText("Write report")
    panel._on_add_task()
    assert panel._columns["todo"].count() == 1

    task = app_ctx.tasks.board(panel._project_id)["todo"][0]
    panel._on_dropped(task.id, "doing", 0)
    assert panel._columns["todo"].count() == 0
    assert panel._columns["doing"].count() == 1
    assert app_ctx.tasks.get_task(task.id).status == "doing"


def test_tasks_panel_double_click_completes(qtbot: QtBot, app_ctx: Any) -> None:
    pid = app_ctx.tasks.create_project("Board").id
    task = app_ctx.tasks.add_task(pid, "Finish me")
    panel = TasksPanel(app_ctx)
    qtbot.addWidget(panel)
    item = panel._columns["todo"].item(0)
    panel._on_complete(item)
    assert app_ctx.tasks.get_task(task.id).is_done


# -- files -----------------------------------------------------------------


def test_files_panel_index_search_preview(qtbot: QtBot, app_ctx: Any, tmp_path: Path) -> None:
    doc = tmp_path / "notes.txt"
    doc.write_text("the quick brown fox jumps over the lazy dog")
    app_ctx.files.index_file(doc, compute_hash=True)

    panel = FilesPanel(app_ctx)
    qtbot.addWidget(panel)
    panel._search.setText("quick")
    assert panel._list.count() == 1

    panel._list.setCurrentRow(0)
    assert "notes.txt" in panel._preview_header.text()
    assert "quick" in panel._preview.toPlainText()


def test_files_panel_find_duplicates(qtbot: QtBot, app_ctx: Any, tmp_path: Path) -> None:
    body = "identical content here"
    first = tmp_path / "a.txt"
    second = tmp_path / "b.txt"
    first.write_text(body)
    second.write_text(body)
    app_ctx.files.index_file(first, compute_hash=True)
    app_ctx.files.index_file(second, compute_hash=True)

    panel = FilesPanel(app_ctx)
    qtbot.addWidget(panel)
    panel._on_find_duplicates()
    # One group header + two file rows.
    assert panel._list.count() == 3


# -- ai --------------------------------------------------------------------


def test_ai_panel_chat_roundtrip(qtbot: QtBot, app_ctx: Any) -> None:
    panel = AIPanel(app_ctx)
    qtbot.addWidget(panel)
    panel._on_new_session()
    assert panel._session_id is not None

    panel._input.setText("hello there")
    panel._on_send()

    session = app_ctx.ai.get_session(panel._session_id)
    roles = [m.role for m in session.messages]
    assert "user" in roles
    assert "assistant" in roles


def test_ai_panel_tools(qtbot: QtBot, app_ctx: Any) -> None:
    panel = AIPanel(app_ctx)
    qtbot.addWidget(panel)
    panel._tools_input.setPlainText("some text to summarise")
    panel._on_summarize()
    assert panel._tools_output.toPlainText() != ""


def test_ai_panel_delete_session(qtbot: QtBot, app_ctx: Any) -> None:
    panel = AIPanel(app_ctx)
    qtbot.addWidget(panel)
    panel._on_new_session()
    panel._on_delete_session()
    assert app_ctx.ai.list_sessions() == []


# -- dashboard -------------------------------------------------------------


def test_dashboard_panel_reflects_state(qtbot: QtBot, app_ctx: Any) -> None:
    app_ctx.notes.create("A")
    app_ctx.notes.create("B")
    pid = app_ctx.tasks.create_project("P").id
    app_ctx.tasks.add_task(pid, "t1")

    panel = DashboardPanel(app_ctx)
    qtbot.addWidget(panel)
    panel.refresh()
    assert panel._cards["notes"]._value.text() == "2"
    assert panel._cards["tasks"]._value.text() == "1"
    assert panel._cards["open_tasks"]._value.text() == "1"


# -- calendar --------------------------------------------------------------


def test_calendar_panel_buckets_due_tasks(qtbot: QtBot, app_ctx: Any) -> None:
    pid = app_ctx.tasks.create_project("P").id
    due = dt.datetime(2026, 7, 15, 9, 0, tzinfo=dt.UTC)
    app_ctx.tasks.add_task(pid, "Deadline", due_at=due)

    panel = CalendarPanel(app_ctx)
    qtbot.addWidget(panel)
    panel._reload_month(2026, 7)
    assert due.date() in panel._by_day
    assert len(panel._highlighted) == 1


# -- automation ------------------------------------------------------------


def test_automation_panel_lists_and_toggles(qtbot: QtBot, app_ctx: Any) -> None:
    app_ctx.automation.create_rule(
        "Notify on note",
        "note.created",
        actions=[ActionSpec(type="notify", params={"message": "hi"})],
    )
    panel = AutomationPanel(app_ctx)
    qtbot.addWidget(panel)
    assert panel._list.count() == 1

    item = panel._list.item(0)
    assert item.checkState() == Qt.CheckState.Checked
    item.setCheckState(Qt.CheckState.Unchecked)  # triggers _on_item_changed
    assert app_ctx.automation.list_rules()[0].enabled is False


def test_automation_new_rule_dialog_values(qtbot: QtBot) -> None:
    from nexus.ui.panels.automation_panel import _NewRuleDialog

    dialog = _NewRuleDialog()
    qtbot.addWidget(dialog)
    dialog._name.setText("My rule")
    dialog._trigger.setCurrentText("task.completed")
    dialog._action.setCurrentText("notify")
    dialog._message.setText("done!")

    name, trigger, action = dialog.values()
    assert name == "My rule"
    assert trigger == "task.completed"
    assert action.type == "notify"
    assert action.params == {"message": "done!"}
