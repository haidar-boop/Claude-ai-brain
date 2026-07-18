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


def test_configure_passes_only_accepted_kwargs() -> None:
    # FakeProvider's constructor has no max_retries/timeout parameter --
    # configure() must silently drop them rather than raising TypeError.
    registry = ProviderRegistry()
    registry.register_factory("fake", FakeProvider)
    instance = registry.configure("fake", model="configured-model", max_retries=5, timeout=30.0)
    assert instance is not None
    assert instance.model == "configured-model"


def test_configure_passes_all_kwargs_to_var_keyword_factory() -> None:
    captured: dict[str, object] = {}

    def factory(**kwargs: object) -> FakeProvider:
        captured.update(kwargs)
        return FakeProvider(model=str(kwargs.get("model", "fake-model")))

    registry = ProviderRegistry()
    registry.register_factory("fake", factory)
    registry.configure("fake", model="m", max_retries=5, timeout=30.0)
    assert captured == {"model": "m", "max_retries": 5, "timeout": 30.0}


def test_configure_returns_none_and_caches_nothing_when_no_kwargs_apply() -> None:
    registry = ProviderRegistry()
    registry.register_factory("fake", FakeProvider)
    result = registry.configure("fake", max_retries=5, timeout=30.0)
    assert result is None
    # No cached instance was seeded -- require() falls through to a fresh
    # zero-argument default construction rather than returning None.
    assert registry.require("fake").model == "fake-model"


def test_configure_raises_provider_not_found_for_unregistered_name() -> None:
    registry = ProviderRegistry()
    with pytest.raises(ProviderNotFoundError):
        registry.configure("missing", model="m")


def test_configure_seeds_cache_for_subsequent_require() -> None:
    registry = ProviderRegistry()
    registry.register_factory("fake", FakeProvider)
    configured = registry.configure("fake", model="configured-model")
    assert registry.require("fake") is configured


def test_get_or_create_returns_one_shared_instance_under_concurrency() -> None:
    # Regression: the instance cache used an unlocked check-then-build-then-
    # write, so concurrent first calls each built their own instance.
    import threading
    import time

    construction_count = 0

    def slow_factory() -> FakeProvider:
        nonlocal construction_count
        construction_count += 1
        time.sleep(0.05)
        return FakeProvider(model="slow-model")

    registry = ProviderRegistry()
    registry.register_factory("slow", slow_factory)
    barrier = threading.Barrier(8)
    results: list[FakeProvider] = []
    results_lock = threading.Lock()

    def worker() -> None:
        barrier.wait()
        instance = registry.get_or_create("slow")
        with results_lock:
            results.append(instance)  # type: ignore[arg-type]

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert construction_count == 1
    assert all(r is results[0] for r in results)
