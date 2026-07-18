"""Layered configuration loading: defaults.toml < aiforge.toml < environment.

Environment variables always win, letting deployment-time overrides (e.g. a
container's env) take precedence over anything checked into version
control, without needing to edit the file.
"""

from __future__ import annotations

import copy
import os
import tomllib
from pathlib import Path
from typing import Any

from aiforge.config.schema import (
    AIForgeConfig,
    EngineConfig,
    ProviderConfig,
    RoutingConfig,
    RoutingRuleConfig,
    SkillsConfig,
)
from aiforge.core.errors import ConfigError

__all__ = ["DEFAULT_CONFIG_PATH", "load_config"]

_ENV_PREFIX = "AIFORGE__"
_DEFAULTS_PATH = Path(__file__).parent / "defaults.toml"
DEFAULT_CONFIG_PATH = Path("aiforge.toml")


def load_config(
    *, project_path: Path | str | None = None, env: dict[str, str] | None = None
) -> AIForgeConfig:
    """Load configuration from shipped defaults, an optional project file, and the environment.

    *project_path* defaults to ``$AIFORGE_CONFIG`` if set, else
    ``./aiforge.toml``; missing project files are silently skipped (not an
    error -- defaults alone are a valid configuration). *env* defaults to
    :data:`os.environ` (injectable for tests).
    """
    resolved_env = os.environ.copy() if env is None else env
    merged = _load_toml(_DEFAULTS_PATH)
    project_file = _resolve_project_path(project_path, resolved_env)
    if project_file is not None and project_file.is_file():
        merged = _deep_merge(merged, _load_toml(project_file))
    merged = _apply_env_overrides(merged, resolved_env)
    return _to_config(merged)


def _resolve_project_path(project_path: Path | str | None, env: dict[str, str]) -> Path | None:
    if project_path is not None:
        return Path(project_path)
    env_path = env.get("AIFORGE_CONFIG")
    if env_path:
        return Path(env_path)
    return DEFAULT_CONFIG_PATH


def _load_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except FileNotFoundError:
        return {}
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {path}: {exc}") from exc


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _apply_env_overrides(data: dict[str, Any], env: dict[str, str]) -> dict[str, Any]:
    result = copy.deepcopy(data)
    for raw_key, raw_value in env.items():
        if not raw_key.startswith(_ENV_PREFIX):
            continue
        path = raw_key[len(_ENV_PREFIX) :].lower().split("__")
        if not all(path):
            continue
        _set_nested(result, path, _coerce_env_value(raw_value))
    return result


def _set_nested(data: dict[str, Any], path: list[str], value: Any) -> None:
    cursor = data
    for key in path[:-1]:
        existing = cursor.get(key)
        if not isinstance(existing, dict):
            existing = {}
            cursor[key] = existing
        cursor = existing
    cursor[path[-1]] = value


def _coerce_env_value(value: str) -> Any:
    lowered = value.strip().lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def _string_list(data: dict[str, Any], field: str, section: str) -> tuple[str, ...]:
    """Read a list-of-strings config field, rejecting a bare string.

    ``tuple("anthropic")`` silently explodes into a tuple of characters, so
    a natural TOML typo like ``fallback_order = "anthropic"`` (missing
    brackets) must raise a clear :class:`ConfigError` instead.
    """
    value = data.get(field, ())
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise ConfigError(
            f"[{section}] {field} must be an array of strings, got {type(value).__name__}"
        )
    return tuple(value)


def _to_config(data: dict[str, Any]) -> AIForgeConfig:
    try:
        engine = EngineConfig(**data.get("engine", {}))
        providers = {name: ProviderConfig(**cfg) for name, cfg in data.get("providers", {}).items()}
        routing_data = data.get("routing", {})
        routing = RoutingConfig(
            rules=tuple(RoutingRuleConfig(**rule) for rule in routing_data.get("rules", [])),
            fallback_order=_string_list(routing_data, "fallback_order", "routing"),
            max_attempts=routing_data.get("max_attempts", 2),
        )
        skills_data = data.get("skills", {})
        skills_enabled = skills_data.get("enabled")
        if skills_enabled is not None and (
            isinstance(skills_enabled, str) or not isinstance(skills_enabled, (list, tuple))
        ):
            raise ConfigError(
                f"[skills] enabled must be an array of strings, got {type(skills_enabled).__name__}"
            )
        skills = SkillsConfig(
            enabled=tuple(skills_enabled) if skills_enabled is not None else None,
            disabled=_string_list(skills_data, "disabled", "skills"),
            extra_dirs=_string_list(skills_data, "extra_dirs", "skills"),
        )
    except (TypeError, AttributeError) as exc:
        raise ConfigError(f"invalid configuration: {exc}") from exc
    return AIForgeConfig(engine=engine, providers=providers, routing=routing, skills=skills)
