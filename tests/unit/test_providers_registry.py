"""Tests for aiforge.providers.registry."""

from __future__ import annotations

import pytest

from aiforge.core.errors import ProviderNotFoundError
from aiforge.providers.fake import FakeProvider
from aiforge.providers.registry import ProviderRegistry


def test_register_factory_and_require() -> None:
    registry = ProviderRegistry()
    registry.register_factory("fake", FakeProvider)
    provider = registry.require("fake")
    assert provider.name == "fake"


def test_require_missing_raises_provider_not_found() -> None:
    registry = ProviderRegistry()
    with pytest.raises(ProviderNotFoundError):
        registry.require("missing")


def test_get_or_create_caches_zero_arg_instance() -> None:
    registry = ProviderRegistry()
    registry.register_factory("fake", FakeProvider)
    first = registry.get_or_create("fake")
    second = registry.get_or_create("fake")
    assert first is second


def test_get_or_create_with_kwargs_bypasses_cache() -> None:
    registry = ProviderRegistry()
    registry.register_factory("fake", FakeProvider)
    first = registry.get_or_create("fake", model="model-a")
    second = registry.get_or_create("fake", model="model-b")
    assert first is not second
    assert first.model == "model-a"
    assert second.model == "model-b"


def test_register_factory_replace_false_raises_on_duplicate() -> None:
    registry = ProviderRegistry()
    registry.register_factory("fake", FakeProvider)
    with pytest.raises(ValueError, match="already registered"):
        registry.register_factory("fake", FakeProvider)


def test_register_factory_replace_true_overrides_and_clears_cache() -> None:
    registry = ProviderRegistry()
    registry.register_factory("fake", FakeProvider)
    original = registry.require("fake")
    registry.register_factory("fake", lambda: FakeProvider(model="new-model"), replace=True)
    replaced = registry.require("fake")
    assert replaced is not original
    assert replaced.model == "new-model"


def test_names_lists_registered_providers_sorted() -> None:
    registry = ProviderRegistry()
    registry.register_factory("zeta", FakeProvider)
    registry.register_factory("alpha", FakeProvider)
    assert registry.names() == ["alpha", "zeta"]


def test_contains() -> None:
    registry = ProviderRegistry()
    registry.register_factory("fake", FakeProvider)
    assert "fake" in registry
    assert "missing" not in registry


def test_discover_entry_points_registers_builtin_providers() -> None:
    registry = ProviderRegistry()
    registry.discover_entry_points()
    assert "fake" in registry
    assert "anthropic" in registry


def test_discover_entry_points_does_not_override_existing_registration() -> None:
    registry = ProviderRegistry()
    sentinel = FakeProvider(model="pre-registered")
    registry.register_factory("fake", lambda: sentinel)
    registry.discover_entry_points()
    assert registry.require("fake") is sentinel
