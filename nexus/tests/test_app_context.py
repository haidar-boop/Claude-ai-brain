"""Tests for the AppContext composition root and config auto-discovery."""

from __future__ import annotations

from pathlib import Path

from nexus.app_context import AppContext


def test_create_autodiscovers_config_in_data_dir(tmp_path: Path) -> None:
    (tmp_path / "config.yaml").write_text("ui:\n  theme: light\n")
    with AppContext.create(data_dir=tmp_path) as ctx:
        assert ctx.config.ui.theme == "light"


def test_create_without_config_uses_defaults(tmp_path: Path) -> None:
    with AppContext.create(data_dir=tmp_path) as ctx:
        assert ctx.config.ui.theme == "dark"


def test_explicit_config_path_overrides_autodiscovery(tmp_path: Path) -> None:
    # A config.yaml sits in the data dir, but an explicit path wins.
    (tmp_path / "config.yaml").write_text("ui:\n  theme: light\n")
    explicit = tmp_path / "other.yaml"
    explicit.write_text("ui:\n  theme: dark\n")
    with AppContext.create(data_dir=tmp_path, config_path=explicit) as ctx:
        assert ctx.config.ui.theme == "dark"


def test_context_wires_every_service(tmp_path: Path) -> None:
    with AppContext.create(data_dir=tmp_path) as ctx:
        for attr in ("notes", "tasks", "files", "ai", "automation", "dashboard"):
            assert getattr(ctx, attr) is not None
        assert ctx.automation_engine is not None
        assert ctx.automation_actions.has("notify")
