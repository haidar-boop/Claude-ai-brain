"""Typed application configuration, loaded from YAML and layered over defaults.

Config is a plain, validated dataclass tree with no dependency on any other
Nexus layer, so it can be loaded and unit-tested in isolation and passed by
constructor injection to whatever needs it. Loading precedence is:
shipped defaults < the user's ``config.yaml`` < a small set of environment
overrides (handy for headless/CI runs). A missing config file is not an
error -- the defaults are themselves a valid configuration.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import Any

import yaml

from nexus.core.errors import ConfigError

__all__ = [
    "AIConfig",
    "ApiConfig",
    "AppConfig",
    "DatabaseConfig",
    "LoggingConfig",
    "UIConfig",
    "load_config",
]

_ENV_PREFIX = "NEXUS_"


@dataclass(frozen=True, slots=True)
class UIConfig:
    """Appearance and window behaviour."""

    theme: str = "dark"  # "dark" | "light"
    window_width: int = 1280
    window_height: int = 800
    remember_layout: bool = True

    def __post_init__(self) -> None:
        if self.theme not in {"dark", "light"}:
            raise ConfigError(f"ui.theme must be 'dark' or 'light', got {self.theme!r}")
        if self.window_width < 640 or self.window_height < 480:
            raise ConfigError("ui window size must be at least 640x480")


@dataclass(frozen=True, slots=True)
class DatabaseConfig:
    """Database, backup, and encryption behaviour."""

    echo_sql: bool = False
    backup_on_start: bool = True
    max_backups: int = 10
    encrypt_sensitive: bool = True

    def __post_init__(self) -> None:
        if self.max_backups < 1:
            raise ConfigError("database.max_backups must be >= 1")


@dataclass(frozen=True, slots=True)
class LoggingConfig:
    """Logging verbosity and sink selection."""

    level: str = "INFO"
    json: bool = False
    to_file: bool = True

    def __post_init__(self) -> None:
        valid = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}
        if self.level.upper() not in valid:
            raise ConfigError(f"logging.level must be one of {sorted(valid)}, got {self.level!r}")


@dataclass(frozen=True, slots=True)
class AIConfig:
    """AI-assistant defaults.

    Credentials are never stored here -- providers read their keys from the
    environment (e.g. ``ANTHROPIC_API_KEY``). ``default_provider = "fake"``
    ships on by default so the assistant works with zero cost and no key
    until the user opts into a real provider.
    """

    default_provider: str = "fake"
    default_model: str | None = None
    embedding_dimensions: int = 256
    max_history_messages: int = 50

    def __post_init__(self) -> None:
        if self.embedding_dimensions < 16:
            raise ConfigError("ai.embedding_dimensions must be >= 16")
        if self.max_history_messages < 1:
            raise ConfigError("ai.max_history_messages must be >= 1")


@dataclass(frozen=True, slots=True)
class ApiConfig:
    """Local REST/WebSocket API server settings (off by default)."""

    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 8770

    def __post_init__(self) -> None:
        if not (1 <= self.port <= 65535):
            raise ConfigError("api.port must be between 1 and 65535")


@dataclass(frozen=True, slots=True)
class AppConfig:
    """The full, validated Nexus configuration."""

    ui: UIConfig = field(default_factory=UIConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    api: ApiConfig = field(default_factory=ApiConfig)


_SECTIONS: dict[str, type[Any]] = {
    "ui": UIConfig,
    "database": DatabaseConfig,
    "logging": LoggingConfig,
    "ai": AIConfig,
    "api": ApiConfig,
}


def _field_names(cls: type[Any]) -> set[str]:
    return {f.name for f in fields(cls)}


def _field_type(cls: type[Any], name: str) -> object:
    return next(f.type for f in fields(cls) if f.name == name)


def load_config(path: Path | str | None = None, *, env: dict[str, str] | None = None) -> AppConfig:
    """Load configuration from *path* (YAML), layered under environment overrides.

    A missing file yields the default configuration. Unknown top-level
    sections or unknown keys within a section raise :class:`ConfigError`
    rather than being silently ignored, so a typo fails loudly at startup
    instead of quietly doing nothing.
    """
    data = _read_yaml(path) if path is not None else {}
    config = _build(data)
    resolved_env = dict(os.environ) if env is None else env
    return _apply_env(config, resolved_env)


def _read_yaml(path: Path | str) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.is_file():
        return {}
    try:
        loaded = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {file_path}: {exc}") from exc
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ConfigError(
            f"config root in {file_path} must be a mapping, got {type(loaded).__name__}"
        )
    return loaded


def _build(data: dict[str, Any]) -> AppConfig:
    unknown = set(data) - set(_SECTIONS)
    if unknown:
        raise ConfigError(f"unknown config section(s): {', '.join(sorted(unknown))}")
    sections: dict[str, Any] = {}
    for name, cls in _SECTIONS.items():
        raw = data.get(name, {})
        if not isinstance(raw, dict):
            raise ConfigError(
                f"config section {name!r} must be a mapping, got {type(raw).__name__}"
            )
        bad_keys = set(raw) - _field_names(cls)
        if bad_keys:
            raise ConfigError(f"unknown key(s) in [{name}]: {', '.join(sorted(bad_keys))}")
        try:
            sections[name] = cls(**raw)
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"invalid [{name}] config: {exc}") from exc
    return AppConfig(**sections)


def _apply_env(config: AppConfig, env: dict[str, str]) -> AppConfig:
    """Apply ``NEXUS_<SECTION>_<KEY>`` overrides (values coerced to field types)."""
    overrides: dict[str, dict[str, Any]] = {name: {} for name in _SECTIONS}
    for raw_key, raw_value in env.items():
        if not raw_key.startswith(_ENV_PREFIX):
            continue
        remainder = raw_key[len(_ENV_PREFIX) :].lower()
        section, _, key = remainder.partition("_")
        cls = _SECTIONS.get(section)
        if cls is None or not key or key not in _field_names(cls):
            continue
        overrides[section][key] = _coerce(raw_value, _field_type(cls, key))
    updated: dict[str, Any] = {}
    for name in _SECTIONS:
        section_obj = getattr(config, name)
        updated[name] = replace(section_obj, **overrides[name]) if overrides[name] else section_obj
    return replace(config, **updated)


def _coerce(value: str, field_type: object) -> Any:
    """Coerce an environment string to the annotated field type."""
    type_name = field_type if isinstance(field_type, str) else getattr(field_type, "__name__", "")
    if "bool" in type_name:
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if "int" in type_name:
        try:
            return int(value)
        except ValueError as exc:
            raise ConfigError(f"expected an integer, got {value!r}") from exc
    return value
