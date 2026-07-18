"""Tests for aiforge.core.errors."""

from __future__ import annotations

import pytest

from aiforge.core import errors


def test_all_errors_inherit_from_base() -> None:
    for name in errors.__all__:
        cls = getattr(errors, name)
        assert issubclass(cls, errors.AIForgeError)


def test_provider_not_found_is_also_registry_error() -> None:
    err = errors.ProviderNotFoundError("openai", available=("anthropic", "fake"))
    assert isinstance(err, errors.ProviderError)
    assert isinstance(err, errors.RegistryError)
    assert "openai" in str(err)
    assert "anthropic" in str(err)
    assert err.name == "openai"
    assert err.available == ("anthropic", "fake")


def test_skill_not_found_is_also_registry_error() -> None:
    err = errors.SkillNotFoundError("elixir")
    assert isinstance(err, errors.SkillError)
    assert isinstance(err, errors.RegistryError)
    assert "elixir" in str(err)


def test_provider_rate_limit_carries_retry_after() -> None:
    err = errors.ProviderRateLimitError("slow down", retry_after=12.5)
    assert err.retry_after == 12.5
    assert isinstance(err, errors.ProviderError)


def test_provider_rate_limit_retry_after_optional() -> None:
    err = errors.ProviderRateLimitError("slow down")
    assert err.retry_after is None


def test_skill_validation_error_includes_source() -> None:
    err = errors.SkillValidationError("missing 'languages' field", source="python/skill.toml")
    assert "python/skill.toml" in str(err)
    assert err.source == "python/skill.toml"


def test_skill_conflict_error_carries_skill_names() -> None:
    err = errors.SkillConflictError("conflicting priorities", skills=("a", "b"))
    assert err.skills == ("a", "b")


def test_config_validation_error_is_config_error() -> None:
    assert issubclass(errors.ConfigValidationError, errors.ConfigError)


@pytest.mark.parametrize(
    "exc_cls",
    [
        errors.AIForgeError,
        errors.ConfigError,
        errors.RegistryError,
        errors.EngineError,
        errors.ProviderError,
        errors.ProviderAuthError,
        errors.ProviderTimeoutError,
        errors.ProviderResponseError,
        errors.SkillError,
    ],
)
def test_simple_errors_accept_plain_message(exc_cls: type[Exception]) -> None:
    err = exc_cls("something went wrong")
    assert str(err) == "something went wrong"
