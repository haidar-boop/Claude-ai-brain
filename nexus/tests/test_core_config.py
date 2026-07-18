"""Tests for nexus.core.config."""

from __future__ import annotations

from pathlib import Path

import pytest

from nexus.core.config import AppConfig, load_config
from nexus.core.errors import ConfigError


def test_defaults_when_no_file() -> None:
    config = load_config(env={})
    assert config.ui.theme == "dark"
    assert config.ai.default_provider == "fake"
    assert config.api.enabled is False


def test_missing_file_uses_defaults(tmp_path: Path) -> None:
    config = load_config(tmp_path / "nope.yaml", env={})
    assert isinstance(config, AppConfig)
    assert config.database.max_backups == 10


def test_yaml_overrides_defaults(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        "ui:\n  theme: light\n  window_width: 1600\nai:\n  default_provider: anthropic\n"
    )
    config = load_config(path, env={})
    assert config.ui.theme == "light"
    assert config.ui.window_width == 1600
    assert config.ai.default_provider == "anthropic"


def test_env_overrides_yaml(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("ui:\n  theme: light\n")
    config = load_config(path, env={"NEXUS_UI_THEME": "dark", "NEXUS_API_PORT": "9001"})
    assert config.ui.theme == "dark"
    assert config.api.port == 9001


def test_env_bool_coercion() -> None:
    config = load_config(env={"NEXUS_API_ENABLED": "true", "NEXUS_DATABASE_ECHO_SQL": "0"})
    assert config.api.enabled is True
    assert config.database.echo_sql is False


def test_unknown_section_raises(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("bogus:\n  x: 1\n")
    with pytest.raises(ConfigError, match="unknown config section"):
        load_config(path, env={})


def test_unknown_key_raises(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("ui:\n  colour: purple\n")
    with pytest.raises(ConfigError, match="unknown key"):
        load_config(path, env={})


def test_invalid_theme_raises(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("ui:\n  theme: rainbow\n")
    with pytest.raises(ConfigError, match=r"ui\.theme"):
        load_config(path, env={})


def test_invalid_port_raises() -> None:
    with pytest.raises(ConfigError, match=r"api\.port"):
        load_config(env={"NEXUS_API_PORT": "70000"})


def test_non_integer_env_int_raises() -> None:
    with pytest.raises(ConfigError, match="expected an integer"):
        load_config(env={"NEXUS_API_PORT": "notanumber"})


def test_yaml_root_must_be_mapping(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("- just\n- a\n- list\n")
    with pytest.raises(ConfigError, match="must be a mapping"):
        load_config(path, env={})
