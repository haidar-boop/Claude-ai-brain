"""Tests for aiforge.utils.cache."""

from __future__ import annotations

import time

import pytest

from aiforge.utils.cache import TTLCache, cached


def test_set_and_get_roundtrip() -> None:
    cache: TTLCache[str, int] = TTLCache(maxsize=4)
    cache.set("a", 1)
    assert cache.get("a") == 1
    assert "a" in cache


def test_missing_key_returns_none() -> None:
    cache: TTLCache[str, int] = TTLCache(maxsize=4)
    assert cache.get("missing") is None
    assert "missing" not in cache


def test_lru_eviction_order() -> None:
    cache: TTLCache[str, int] = TTLCache(maxsize=2)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.get("a")  # touch "a" so "b" becomes the least-recently-used entry
    cache.set("c", 3)  # should evict "b", not "a"
    assert "a" in cache
    assert "b" not in cache
    assert "c" in cache


def test_ttl_expiry() -> None:
    cache: TTLCache[str, int] = TTLCache(maxsize=4, ttl=0.05)
    cache.set("a", 1)
    assert cache.get("a") == 1
    time.sleep(0.08)
    assert cache.get("a") is None
    assert len(cache) == 0


def test_hits_and_misses_tracked() -> None:
    cache: TTLCache[str, int] = TTLCache(maxsize=4)
    cache.set("a", 1)
    cache.get("a")
    cache.get("missing")
    assert cache.hits == 1
    assert cache.misses == 1
    assert cache.hit_rate == pytest.approx(0.5)


def test_hit_rate_with_no_lookups_is_zero() -> None:
    cache: TTLCache[str, int] = TTLCache(maxsize=4)
    assert cache.hit_rate == 0.0


def test_clear_empties_cache() -> None:
    cache: TTLCache[str, int] = TTLCache(maxsize=4)
    cache.set("a", 1)
    cache.clear()
    assert len(cache) == 0
    assert cache.get("a") is None


@pytest.mark.parametrize("maxsize", [0, -1])
def test_invalid_maxsize_raises(maxsize: int) -> None:
    with pytest.raises(ValueError, match="maxsize"):
        TTLCache(maxsize=maxsize)


@pytest.mark.parametrize("ttl", [0, -1.0])
def test_invalid_ttl_raises(ttl: float) -> None:
    with pytest.raises(ValueError, match="ttl"):
        TTLCache(maxsize=4, ttl=ttl)


def test_cached_decorator_memoizes() -> None:
    calls: list[int] = []

    @cached(maxsize=4)
    def expensive(x: int) -> int:
        calls.append(x)
        return x * 2

    assert expensive(2) == 4
    assert expensive(2) == 4
    assert calls == [2]


def test_cached_decorator_distinguishes_kwargs() -> None:
    @cached(maxsize=4)
    def f(x: int, *, y: int = 0) -> int:
        return x + y

    assert f(1, y=2) == 3
    assert f(1, y=3) == 4
    assert f.cache.misses == 2  # type: ignore[attr-defined]
