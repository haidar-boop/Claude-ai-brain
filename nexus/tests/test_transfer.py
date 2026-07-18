"""Tests for workspace export/import round-tripping."""

from __future__ import annotations

import datetime as dt
import zipfile
from pathlib import Path
from typing import Any

import pytest

from nexus.app_context import AppContext
from nexus.automation.rules import ActionSpec, Condition
from nexus.core.errors import ExportError
from nexus.services.transfer import export_workspace, import_workspace


@pytest.fixture
def context() -> Any:
    ctx = AppContext.in_memory()
    try:
        yield ctx
    finally:
        ctx.close()


def _seed(ctx: AppContext) -> None:
    ctx.notes.create("First", "body one", tags=["a", "b"])
    ctx.notes.create("Second", "body two")
    pid = ctx.tasks.create_project("Work", "the project").id
    ctx.tasks.add_task(pid, "todo task")
    due = dt.datetime(2026, 8, 1, 12, 0, tzinfo=dt.UTC)
    done = ctx.tasks.add_task(pid, "done task", due_at=due)
    ctx.tasks.complete(done.id)
    ctx.automation.create_rule(
        "notify rule",
        "note.created",
        conditions=[Condition(field="title", op="exists", value=True)],
        actions=[ActionSpec(type="notify", params={"message": "hi"})],
    )


def test_export_creates_zip_with_workspace_json(context: Any, tmp_path: Path) -> None:
    _seed(context)
    archive = tmp_path / "ws.zip"
    summary = export_workspace(context, archive)

    assert archive.is_file()
    with zipfile.ZipFile(archive) as zf:
        assert "workspace.json" in zf.namelist()
    assert summary.notes == 2
    assert summary.projects == 1
    assert summary.tasks == 2
    assert summary.rules == 1


def test_round_trip_into_fresh_workspace(context: Any, tmp_path: Path) -> None:
    _seed(context)
    archive = tmp_path / "ws.zip"
    export_workspace(context, archive)

    fresh = AppContext.in_memory()
    try:
        summary = import_workspace(fresh, archive)
        assert summary.notes == 2
        assert summary.tasks == 2

        titles = {n.title for n in fresh.notes.list_notes()}
        assert titles == {"First", "Second"}

        first = next(n for n in fresh.notes.list_notes() if n.title == "First")
        assert set(first.tags) == {"a", "b"}

        projects = fresh.tasks.list_projects()
        assert len(projects) == 1
        board = fresh.tasks.board(projects[0].id)
        all_tasks = [t for column in board.values() for t in column]
        assert len(all_tasks) == 2
        assert any(t.is_done for t in all_tasks)

        rules = fresh.automation.list_rules()
        assert len(rules) == 1
        assert rules[0].trigger == "note.created"
        assert rules[0].actions[0].type == "notify"
    finally:
        fresh.close()


def test_import_missing_file_raises(context: Any, tmp_path: Path) -> None:
    with pytest.raises(ExportError, match="no such export archive"):
        import_workspace(context, tmp_path / "absent.zip")


def test_import_non_zip_raises(context: Any, tmp_path: Path) -> None:
    bogus = tmp_path / "not.zip"
    bogus.write_text("plain text, not a zip")
    with pytest.raises(ExportError, match="not a valid ZIP"):
        import_workspace(context, bogus)


def test_import_wrong_version_raises(context: Any, tmp_path: Path) -> None:
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("workspace.json", '{"nexus_export_version": 999}')
    with pytest.raises(ExportError, match="unsupported export version"):
        import_workspace(context, archive)


def test_import_missing_member_raises(context: Any, tmp_path: Path) -> None:
    archive = tmp_path / "empty.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("something_else.txt", "nope")
    with pytest.raises(ExportError, match="missing"):
        import_workspace(context, archive)
