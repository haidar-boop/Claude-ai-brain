"""Tests for aiforge.api.cli."""

from __future__ import annotations

from pathlib import Path

import pytest

from aiforge.api.cli import main


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0
    assert "aiforge" in capsys.readouterr().out


def test_version_subcommand(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["version"])
    assert exit_code == 0
    assert capsys.readouterr().out.strip()


def test_no_command_prints_help_and_returns_nonzero(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([])
    assert exit_code == 1
    assert "usage" in capsys.readouterr().out.lower()


def test_run_with_fake_provider(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    exit_code = main(["run", "hello there", "--provider", "fake"])
    assert exit_code == 0
    assert "hello there" in capsys.readouterr().out


def test_run_stream_with_fake_provider(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    exit_code = main(["run", "streaming hello", "--provider", "fake", "--stream"])
    assert exit_code == 0
    assert "streaming hello" in capsys.readouterr().out


def test_providers_list_includes_fake_and_anthropic(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["providers", "list"])
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "fake" in output
    assert "anthropic" in output


def test_skills_list_runs_without_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    exit_code = main(["skills", "list"])
    assert exit_code == 0


def test_config_show_prints_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    exit_code = main(["config", "show"])
    assert exit_code == 0
    output = capsys.readouterr().out
    assert '"default_provider"' in output


def test_config_path_prints_default(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    exit_code = main(["config", "path"])
    assert exit_code == 0
    assert "aiforge.toml" in capsys.readouterr().out


def test_config_path_respects_explicit_flag(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["--config", "/tmp/custom.toml", "config", "path"])
    assert exit_code == 0
    assert "/tmp/custom.toml" in capsys.readouterr().out


def test_unknown_provider_reports_error_not_traceback(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["run", "hi", "--provider", "does-not-exist"])
    assert exit_code == 1
    assert "error" in capsys.readouterr().err.lower()
