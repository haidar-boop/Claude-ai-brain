"""Tests for aiforge.core.registry."""

from __future__ import annotations

import pytest

from aiforge.core.registry import Registry


def test_register_and_get() -> None:
    registry: Registry[str] = Registry(kind="widget")
    registry.register("a", "value-a")
    assert registry.get("a") == "value-a"


def test_get_missing_returns_none() -> None:
    registry: Registry[str] = Registry()
    assert registry.get("missing") is None


def test_require_missing_raises_key_error_with_available_names() -> None:
    registry: Registry[str] = Registry(kind="widget")
    registry.register("a", "value-a")
    registry.register("b", "value-b")
    with pytest.raises(KeyError, match="widget") as exc_info:
        registry.require("missing")
    message = str(exc_info.value)
    assert "a" in message
    assert "b" in message


def test_duplicate_registration_raises_by_default() -> None:
    registry: Registry[str] = Registry()
    registry.register("a", "first")
    with pytest.raises(ValueError, match="already registered"):
        registry.register("a", "second")


def test_replace_true_allows_overwrite() -> None:
    registry: Registry[str] = Registry()
    registry.register("a", "first")
    registry.register("a", "second", replace=True)
    assert registry.get("a") == "second"


def test_unregister_removes_item() -> None:
    registry: Registry[str] = Registry()
    registry.register("a", "value")
    registry.unregister("a")
    assert "a" not in registry
    assert registry.get("a") is None


def test_unregister_missing_is_noop() -> None:
    registry: Registry[str] = Registry()
    registry.unregister("missing")


def test_names_are_sorted() -> None:
    registry: Registry[str] = Registry()
    registry.register("zebra", "z")
    registry.register("apple", "a")
    assert registry.names() == ["apple", "zebra"]


def test_items_yields_pairs() -> None:
    registry: Registry[int] = Registry()
    registry.register("one", 1)
    registry.register("two", 2)
    assert dict(registry.items()) == {"one": 1, "two": 2}


def test_len_and_contains() -> None:
    registry: Registry[int] = Registry()
    registry.register("a", 1)
    assert len(registry) == 1
    assert "a" in registry
    assert "b" not in registry


def test_iter_yields_sorted_names() -> None:
    registry: Registry[int] = Registry()
    registry.register("b", 2)
    registry.register("a", 1)
    assert list(registry) == ["a", "b"]
