"""Typed configuration schema.

Plain data -- this module has no dependency on the provider or skill
layers, so config can be loaded, validated, and unit-tested independently.
Something that depends on both (typically :mod:`aiforge.core.engine` or
:mod:`aiforge.api.client`) is responsible for translating this schema into
concrete provider/skill objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "AIForgeConfig",
    "EngineConfig",
    "ProviderConfig",
    "RoutingConfig",
    "RoutingRuleConfig",
    "SkillsConfig",
]


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    """Settings for a single named provider."""

    model: str | None = None
    max_tokens: int = 4096
    max_retries: int = 2
    timeout: float = 600.0
    extra: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RoutingRuleConfig:
    """A single routing rule: send matching requests to *provider* (+ optional *model*)."""

    match: str
    provider: str
    model: str | None = None


@dataclass(frozen=True, slots=True)
class RoutingConfig:
    """Cross-provider routing policy."""

    rules: tuple[RoutingRuleConfig, ...] = ()
    fallback_order: tuple[str, ...] = ()
    max_attempts: int = 2


@dataclass(frozen=True, slots=True)
class SkillsConfig:
    """Which skills are enabled and where to look for additional ones."""

    enabled: tuple[str, ...] | None = None
    """Explicit allowlist of skill names. ``None`` means "all discovered
    skills are enabled" (the default); an empty tuple means "none"."""
    disabled: tuple[str, ...] = ()
    extra_dirs: tuple[str, ...] = ()
    """Additional directories to scan for ``skill.toml`` manifests, beyond
    the built-in skills directory."""


@dataclass(frozen=True, slots=True)
class EngineConfig:
    """Core engine behavior."""

    default_provider: str = "anthropic"


@dataclass(frozen=True, slots=True)
class AIForgeConfig:
    """The full, merged AIForge configuration."""

    engine: EngineConfig = field(default_factory=EngineConfig)
    providers: dict[str, ProviderConfig] = field(default_factory=dict)
    routing: RoutingConfig = field(default_factory=RoutingConfig)
    skills: SkillsConfig = field(default_factory=SkillsConfig)

    def provider_config(self, name: str) -> ProviderConfig:
        """Return the config for *name*, or a default :class:`ProviderConfig` if unset."""
        return self.providers.get(name, ProviderConfig())
