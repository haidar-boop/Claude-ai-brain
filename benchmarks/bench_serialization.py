"""Benchmark: aiforge.utils.serialization (orjson-accelerated) vs. plain stdlib json.

Run with: pytest benchmarks/bench_serialization.py --benchmark-only

Install the ``fast`` extra (``pip install aiforge[fast]``) to exercise the
orjson-accelerated path; without it, ``dumps``/``loads`` fall back to stdlib
``json`` and this benchmark mainly documents that the fallback has no
measurable overhead of its own.
"""

from __future__ import annotations

import json

from aiforge.utils.serialization import HAS_ORJSON, dumps, loads

_PAYLOAD = {
    "text": "This is a representative provider response payload. " * 20,
    "model": "claude-opus-4-8",
    "provider": "anthropic",
    "usage": {"input_tokens": 512, "output_tokens": 1024, "total_tokens": 1536},
    "cost_usd": 0.0421,
    "stop_reason": "end_turn",
    "metadata": {"skills": ["python", "sql"], "retries": 0},
}
_SERIALIZED = dumps(_PAYLOAD)


def test_bench_dumps_aiforge(benchmark) -> None:
    benchmark(dumps, _PAYLOAD)


def test_bench_dumps_stdlib_json(benchmark) -> None:
    benchmark(json.dumps, _PAYLOAD)


def test_bench_loads_aiforge(benchmark) -> None:
    benchmark(loads, _SERIALIZED)


def test_bench_loads_stdlib_json(benchmark) -> None:
    benchmark(json.loads, _SERIALIZED)


def test_reports_whether_orjson_is_active() -> None:
    print(f"\norjson acceleration active: {HAS_ORJSON}")
