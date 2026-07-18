"""LRU+TTL cache: a small, dependency-free cache for hot-path lookups.

Used for optional response caching, skill-manifest parsing, and anywhere a
stable key maps to an expensive-to-recompute value. ``None`` is not
distinguished from "not cached" -- none of AIForge's own use cases ever
legitimately cache ``None``, and dropping that distinction keeps the
implementation simple.
"""

from __future__ import annotations

import functools
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Hashable
from typing import Generic, ParamSpec, TypeVar

K = TypeVar("K", bound=Hashable)
V = TypeVar("V")
P = ParamSpec("P")
R = TypeVar("R")

__all__ = ["TTLCache", "cached"]


class TTLCache(Generic[K, V]):
    """Thread-safe cache with LRU eviction and an optional per-entry TTL."""

    def __init__(self, maxsize: int = 128, ttl: float | None = None) -> None:
        if maxsize < 1:
            raise ValueError("maxsize must be >= 1")
        if ttl is not None and ttl <= 0:
            raise ValueError("ttl must be > 0 when provided")
        self._maxsize = maxsize
        self._ttl = ttl
        self._data: OrderedDict[K, tuple[V, float | None]] = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: K) -> V | None:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                self.misses += 1
                return None
            value, expires_at = entry
            if expires_at is not None and expires_at <= time.monotonic():
                del self._data[key]
                self.misses += 1
                return None
            self._data.move_to_end(key)
            self.hits += 1
            return value

    def set(self, key: K, value: V) -> None:
        expires_at = time.monotonic() + self._ttl if self._ttl is not None else None
        with self._lock:
            self._data[key] = (value, expires_at)
            self._data.move_to_end(key)
            while len(self._data) > self._maxsize:
                self._data.popitem(last=False)

    def __contains__(self, key: K) -> bool:
        return self.get(key) is not None

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0


def cached(
    *, maxsize: int = 128, ttl: float | None = None
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator that memoizes a function's return value via :class:`TTLCache`.

    The wrapped callable's positional and keyword arguments must be hashable.
    The underlying cache is reachable as ``wrapped.cache`` for introspection
    or manual invalidation.
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        cache: TTLCache[tuple[object, ...], R] = TTLCache(maxsize=maxsize, ttl=ttl)

        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            key = (args, tuple(sorted(kwargs.items())))
            cached_value = cache.get(key)
            if cached_value is not None:
                return cached_value
            result = func(*args, **kwargs)
            cache.set(key, result)
            return result

        wrapper.cache = cache  # type: ignore[attr-defined]
        return wrapper

    return decorator
