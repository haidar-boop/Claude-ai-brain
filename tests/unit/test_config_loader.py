"""Tests for aiforge.config.loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from aiforge.config.loader import load_config
from aiforge.core.errors import ConfigError


def test_load_config_with_no_project_file_uses_defaults(tmp_path: Path) -> None:
    missing = tmp_path / "aiforge.toml"
    config = load_config(project_path=missing, env={})
    assert config.engine.default_provider == "anthropic"
    assert config.provider_config("anthropic").model == "claude-opus-4-8"


def test_project_file_overrides_defaults(tmp_path: Path) -> None:
    project = tmp_path / "aiforge.toml"
    project.write_text('[engine]\ndefault_provider = "fake"\n')
    config = load_config(project_path=project, env={})
    assert config.engine.default_provider == "fake"
    assert config.provider_config("anthropic").model == "claude-opus-4-8"


def test_env_overrides_project_file(tmp_path: Path) -> None:
    project = tmp_path / "aiforge.toml"
    project.write_text('[engine]\ndefault_provider = "fake"\n')
    config = load_config(
        project_path=project, env={"AIFORGE__ENGINE__DEFAULT_PROVIDER": "anthropic"}
    )
    assert config.engine.default_provider == "anthropic"


def test_env_override_creates_nested_provider_config(tmp_path: Path) -> None:
    missing = tmp_path / "aiforge.toml"
    config = load_config(
        project_path=missing, env={"AIFORGE__PROVIDERS__ANTHROPIC__MAX_RETRIES": "5"}
    )
    assert config.provider_config("anthropic").max_retries == 5
    assert config.provider_config("anthropic").model == "claude-opus-4-8"


def test_env_values_are_type_coerced(tmp_path: Path) -> None:
    missing = tmp_path / "aiforge.toml"
    config = load_config(
        project_path=missing,
        env={
            "AIFORGE__PROVIDERS__ANTHROPIC__MAX_RETRIES": "7",
            "AIFORGE__PROVIDERS__ANTHROPIC__TIMEOUT": "12.5",
        },
    )
    provider = config.provider_config("anthropic")
    assert provider.max_retries == 7
    assert isinstance(provider.max_retries, int)
    assert provider.timeout == 12.5
    assert isinstance(provider.timeout, float)


def test_unrelated_env_vars_are_ignored(tmp_path: Path) -> None:
    missing = tmp_path / "aiforge.toml"
    config = load_config(project_path=missing, env={"PATH": "/usr/bin", "HOME": "/root"})
    assert config.engine.default_provider == "anthropic"


def test_invalid_toml_raises_config_error(tmp_path: Path) -> None:
    project = tmp_path / "aiforge.toml"
    project.write_text("this is not [valid toml")
    with pytest.raises(ConfigError):
        load_config(project_path=project, env={})


def test_routing_rules_are_parsed(tmp_path: Path) -> None:
    project = tmp_path / "aiforge.toml"
    project.write_text(
        '[[routing.rules]]\nmatch = "rust"\nprovider = "anthropic"\nmodel = "claude-opus-4-8"\n'
    )
    config = load_config(project_path=project, env={})
    assert len(config.routing.rules) == 1
    assert config.routing.rules[0].match == "rust"


def test_skills_enabled_list_is_parsed(tmp_path: Path) -> None:
    project = tmp_path / "aiforge.toml"
    project.write_text('[skills]\nenabled = ["python", "typescript"]\n')
    config = load_config(project_path=project, env={})
    assert config.skills.enabled == ("python", "typescript")


def test_config_path_env_var_is_used_when_project_path_not_passed(tmp_path: Path) -> None:
    project = tmp_path / "custom.toml"
    project.write_text('[engine]\ndefault_provider = "fake"\n')
    config = load_config(env={"AIFORGE_CONFIG": str(project)})
    assert config.engine.default_provider == "fake"


def test_bare_string_fallback_order_raises_instead_of_exploding_into_chars(
    tmp_path: Path,
) -> None:
    # Regression: tuple("anthropic") silently became ('a','n','t',...) --
    # a natural TOML typo (missing array brackets) must be a clear error.
    project = tmp_path / "aiforge.toml"
    project.write_text('[routing]\nfallback_order = "anthropic"\n')
    with pytest.raises(ConfigError, match="fallback_order must be an array"):
        load_config(project_path=project, env={})


def test_bare_string_skills_enabled_raises(tmp_path: Path) -> None:
    project = tmp_path / "aiforge.toml"
    project.write_text('[skills]\nenabled = "python"\n')
    with pytest.raises(ConfigError, match="enabled must be an array"):
        load_config(project_path=project, env={})


def test_bare_string_skills_disabled_raises(tmp_path: Path) -> None:
    project = tmp_path / "aiforge.toml"
    project.write_text('[skills]\ndisabled = "rust"\n')
    with pytest.raises(ConfigError, match="disabled must be an array"):
        load_config(project_path=project, env={})
