"""Benchmark: cold-start import cost, optimized (lazy) vs. a naive eager baseline.

"Optimized" = ``import aiforge`` as shipped: the top-level package uses PEP 562
lazy attribute access (see ``aiforge/__init__.py``), so importing it does not
import the provider layer, the Anthropic SDK, or parse any skill manifests.

"Naive baseline" = a documented equivalent of what a non-lazy package would pay
at import time: eagerly importing the engine, provider, and skill subsystems
and running skill discovery (parsing all 10 built-in ``skill.toml`` files).
This is not a prior version of aiforge -- it is what "no lazy loading" would
cost, measured with the same subprocess methodology for a fair comparison.

Each round pays subprocess-spawn overhead on top of the import itself, so
these numbers are useful for the *relative* optimized-vs-naive comparison,
not as an absolute "aiforge costs N ms" figure. See
``scripts/measure_startup.py`` for an averaged, human-readable report
(including peak memory) without pytest-benchmark's per-round spawn cost
skewing the picture.

Run with: pytest benchmarks/bench_startup.py --benchmark-only
"""

from __future__ import annotations

import subprocess
import sys

_OPTIMIZED_CODE = "import aiforge"
_NAIVE_BASELINE_CODE = (
    "from aiforge.core.engine import Engine\n"
    "from aiforge.api.client import AIForge\n"
    "from aiforge.providers.registry import ProviderRegistry\n"
    "from aiforge.skills.loader import discover_skills\n"
    "discover_skills()\n"
)


def _run_import(code: str) -> None:
    subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, timeout=30)


def test_bench_optimized_lazy_import(benchmark) -> None:
    benchmark(_run_import, _OPTIMIZED_CODE)


def test_bench_naive_eager_import(benchmark) -> None:
    benchmark(_run_import, _NAIVE_BASELINE_CODE)
