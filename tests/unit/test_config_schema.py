"""Tests for aiforge.config.schema."""

from __future__ import annotations

from aiforge.config.schema import (
    AIForgeConfig,
    EngineConfig,
    ProviderConfig,
    RoutingConfig,
    RoutingRuleConfig,
    SkillsConfig,
)


def test_provider_config_defaults() -> None:
    config = ProviderConfig()
    assert config.model is None
    assert config.max_tokens == 4096
    assert config.max_retries == 2
    assert config.timeout == 600.0
    assert config.extra == {}


def test_routing_rule_config_model_optional() -> None:
    rule = RoutingRuleConfig(match="rust", provider="anthropic")
    assert rule.model is None


def test_routing_config_defaults() -> None:
    routing = RoutingConfig()
    assert routing.rules == ()
    assert routing.fallback_order == ()
    assert routing.max_attempts == 2


def test_skills_config_enabled_none_means_all() -> None:
    skills = SkillsConfig()
    assert skills.enabled is None
    assert skills.disabled == ()
    assert skills.extra_dirs == ()


def test_engine_config_default_provider() -> None:
    assert EngineConfig().default_provider == "anthropic"


def test_aiforge_config_defaults() -> None:
    config = AIForgeConfig()
    assert config.engine.default_provider == "anthropic"
    assert config.providers == {}
    assert config.routing.rules == ()
    assert config.skills.enabled is None


def test_provider_config_lookup_returns_default_when_unset() -> None:
    config = AIForgeConfig()
    assert config.provider_config("anthropic") == ProviderConfig()


def test_provider_config_lookup_returns_configured_value() -> None:
    custom = ProviderConfig(model="claude-haiku-4-5")
    config = AIForgeConfig(providers={"anthropic": custom})
    assert config.provider_config("anthropic") is custom
