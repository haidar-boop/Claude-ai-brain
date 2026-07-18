"""Standalone startup-cost report: no pytest, no extra dependencies required.

Prints wall-clock import time and peak RSS memory for the optimized (lazy)
``import aiforge`` path versus a naive eager-import baseline, each averaged
over a few subprocess runs. This is the source of the numbers quoted in
``docs/performance.md`` and the README.

Run with: python scripts/measure_startup.py
"""

from __future__ import annotations

import statistics
import subprocess  # nosec B404 -- fixed argv below, no untrusted input
import sys

_RUNS = 5

_OPTIMIZED_CODE = "import aiforge"
_NAIVE_BASELINE_CODE = (
    "from aiforge.core.engine import Engine\n"
    "from aiforge.api.client import AIForge\n"
    "from aiforge.providers.registry import ProviderRegistry\n"
    "from aiforge.skills.loader import discover_skills\n"
    "discover_skills()\n"
)

# resource.ru_maxrss is reported in KiB on Linux but bytes on macOS; this
# script assumes Linux (the project's documented dev/CI platform).
_CHILD_TEMPLATE = (
    "import resource, time\n"
    "_start = time.perf_counter()\n"
    "{code}\n"
    "_elapsed_ms = (time.perf_counter() - _start) * 1000\n"
    "_peak_kib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss\n"
    "print(f'{{_elapsed_ms}} {{_peak_kib}}')\n"
)


def _measure_once(code: str) -> tuple[float, int]:
    script = _CHILD_TEMPLATE.format(code=code)
    # sys.executable + a fixed, locally-built script string, no untrusted input.
    result = subprocess.run(  # nosec B603
        [sys.executable, "-c", script], check=True, capture_output=True, text=True, timeout=30
    )
    elapsed_str, peak_kib_str = result.stdout.strip().split()
    return float(elapsed_str), int(peak_kib_str)


def _measure(label: str, code: str) -> None:
    timings = []
    peaks = []
    for _ in range(_RUNS):
        elapsed_ms, peak_kib = _measure_once(code)
        timings.append(elapsed_ms)
        peaks.append(peak_kib)
    print(f"{label}:")
    print(
        f"  import time: mean={statistics.mean(timings):.1f} ms  "
        f"min={min(timings):.1f} ms  (n={_RUNS})"
    )
    print(
        f"  peak RSS:    mean={statistics.mean(peaks) / 1024:.1f} MiB  "
        f"min={min(peaks) / 1024:.1f} MiB"
    )


def main() -> int:
    print(f"Python {sys.version.split()[0]} on {sys.platform}\n")
    _measure("optimized (lazy `import aiforge`)", _OPTIMIZED_CODE)
    print()
    _measure("naive baseline (eager engine+providers+skills import)", _NAIVE_BASELINE_CODE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
