"""Benchmark: TTLCache-backed memoization vs. no caching, plus memory overhead.

Run with: pytest benchmarks/bench_cache.py --benchmark-only
"""

from __future__ import annotations

import tracemalloc

from aiforge.utils.cache import TTLCache, cached

_calls = 0


def _expensive(n: int) -> int:
    global _calls
    _calls += 1
    return sum(i * i for i in range(n))


@cached(maxsize=256, ttl=60.0)
def _expensive_cached(n: int) -> int:
    return _expensive(n)


def test_bench_uncached_repeated_calls(benchmark) -> None:
    benchmark(lambda: [_expensive(500) for _ in range(20)])


def test_bench_cached_repeated_calls(benchmark) -> None:
    # Same key every call: after the first-ever miss, every call in every
    # round is a cache hit -- this measures steady-state hit cost, the
    # realistic case for memoizing a stable, repeatedly-requested value.
    benchmark(lambda: [_expensive_cached(500) for _ in range(20)])


def test_cache_hit_avoids_recomputation() -> None:
    global _calls
    _calls = 0
    for _ in range(50):
        _expensive_cached(777)
    assert _calls == 1


def test_ttl_cache_memory_overhead_for_1000_entries() -> None:
    tracemalloc.start()
    baseline_current, _ = tracemalloc.get_traced_memory()
    cache: TTLCache[int, str] = TTLCache(maxsize=1000, ttl=60.0)
    for i in range(1000):
        cache.set(i, f"value-{i}")
    current, _peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    per_entry_bytes = (current - baseline_current) / 1000
    print(f"\nTTLCache: ~{per_entry_bytes:.0f} bytes/entry for 1000 small string entries")
    assert per_entry_bytes < 2000  # sanity bound, not a strict perf gate
