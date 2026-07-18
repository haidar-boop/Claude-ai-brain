"""Tests for the command-line interface.

Each ``main(...)`` call builds a real on-disk context under a temp data
directory, so successive calls in one test share state through the database
file -- exactly as a user running the command twice would.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nexus import cli


def _run(tmp: Path, *args: str) -> int:
    return cli.main(["--data-dir", str(tmp), *args])


def test_version_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert "nexus" in capsys.readouterr().out


def test_notes_add_and_list(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _run(tmp_path, "notes", "add", "Groceries", "--tags", "home,food") == 0
    assert "created note" in capsys.readouterr().out

    assert _run(tmp_path, "notes", "list") == 0
    out = capsys.readouterr().out
    assert "Groceries" in out
    assert "home" in out


def test_notes_list_empty(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _run(tmp_path, "notes", "list") == 0
    assert "(no notes)" in capsys.readouterr().out


def test_tasks_flow(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # No projects yet.
    assert _run(tmp_path, "tasks", "projects") == 0
    assert "(no projects)" in capsys.readouterr().out

    # Create a project directly, then add via the CLI and show the board.
    from nexus.app_context import AppContext

    with AppContext.create(data_dir=tmp_path) as ctx:
        pid = ctx.tasks.create_project("Chores").id

    assert _run(tmp_path, "tasks", "add", str(pid), "Take out bins") == 0
    assert "created task" in capsys.readouterr().out

    assert _run(tmp_path, "tasks", "board", str(pid)) == 0
    board_out = capsys.readouterr().out
    assert "TODO" in board_out
    assert "Take out bins" in board_out


def test_export_import_between_data_dirs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "source"
    dest = tmp_path / "dest"
    archive = tmp_path / "ws.zip"

    assert _run(source, "notes", "add", "Portable") == 0
    capsys.readouterr()
    assert _run(source, "export", str(archive)) == 0
    assert "exported" in capsys.readouterr().out
    assert archive.is_file()

    assert _run(dest, "import", str(archive)) == 0
    assert "imported" in capsys.readouterr().out

    assert _run(dest, "notes", "list") == 0
    assert "Portable" in capsys.readouterr().out


def test_plugins_lists_none(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _run(tmp_path, "plugins") == 0
    assert "(no plugins installed)" in capsys.readouterr().out


def test_gui_command_dispatches_to_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict[str, object] = {}

    def fake_run(**kwargs: object) -> int:
        called.update(kwargs)
        return 0

    import nexus.ui.app as app_module

    monkeypatch.setattr(app_module, "run", fake_run)
    assert cli.main(["--data-dir", str(tmp_path), "gui"]) == 0
    assert called == {"data_dir": str(tmp_path), "config_path": None}
