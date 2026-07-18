# Performance Report

AIForge is a greenfield project: there is no prior release or prior commit to diff these numbers
against. Every result below instead compares the shipped, optimized implementation of a feature
against a **documented naive baseline** — a straightforward, unoptimized implementation of the same
feature (eager imports instead of lazy, no cache, a linear scan instead of an index, stdlib `json`
instead of an accelerated path). The baseline code lives next to the optimized code in each
benchmark file, so it can be read and checked directly rather than taken on faith.

All numbers were measured on one machine running **Python 3.11.15 on Linux**, with the optional
`fast` extra (`orjson`) installed. They will vary on other hardware and Python builds — see
[Reproducing these numbers](#reproducing-these-numbers) to regenerate them locally. Four sources
produced everything in this document:

| Source | What it measures |
|---|---|
| `scripts/measure_startup.py` | Import wall-clock time and peak RSS, 5 subprocess runs averaged |
| `benchmarks/bench_startup.py` | The same comparison via `pytest-benchmark`, as a cross-check |
| `benchmarks/bench_cache.py` | `TTLCache`/`@cached` hit cost vs. no caching, plus memory overhead |
| `benchmarks/bench_serialization.py` | `aiforge.utils.serialization` vs. stdlib `json` |
| `benchmarks/bench_skill_loading.py` | Cold skill discovery, and indexed vs. linear-scan resolution |

`benchmarks/README.md` carries the same methodology notes in more compact form; this document
walks through the *why* behind each number using the actual implementation.

## At a glance

| Technique | Optimized | Naive baseline | Factor |
|---|---|---|---|
| Startup (`measure_startup.py`) | 9.9 ms mean import / 11.2 MiB peak RSS | 88.0 ms mean import / 23.0 MiB peak RSS | ~8.9x faster, ~2.1x less memory |
| Startup (`bench_startup.py` cross-check) | 23.5 ms mean | 117.2 ms mean | ~5.0x faster |
| Caching (`bench_cache.py`) | 14.0 µs/round warm | 291.6 µs/round uncached | ~20.8x faster |
| Serialization `dumps` (`bench_serialization.py`) | 0.69 µs | 5.45 µs | ~7.9x faster |
| Serialization `loads` (`bench_serialization.py`) | 1.30 µs | 3.42 µs | ~2.6x faster |
| Skill resolution (`bench_skill_loading.py`) | 18.97 µs indexed | 19.51 µs linear scan | negligible at 10 skills — see below |

## Startup cost: lazy imports

`import aiforge` uses [PEP 562](https://peps.python.org/pep-0562/) module-level `__getattr__` /
`__dir__` so that importing the top-level package does not import the provider layer, the skill
layer, or parse a single `skill.toml`. `src/aiforge/__init__.py` builds its lazy `__getattr__`
from a name → `(module, attribute)` table:

```python
_LAZY_ATTRS: dict[str, tuple[str, str]] = {
    "AIForge": ("aiforge.api.client", "AIForge"),
    "AIForgeConfig": ("aiforge.config.schema", "AIForgeConfig"),
    "Engine": ("aiforge.core.engine", "Engine"),
    "ChatRequest": ("aiforge.providers.types", "ChatRequest"),
    # ...ChatResponse, Message, Role, Usage, SkillManifest
}

__getattr__ = lazy_getattr(__name__, _LAZY_ATTRS)
__dir__ = lazy_dir([*__all__])
```

`lazy_getattr` (`src/aiforge/utils/lazy.py`) resolves a name only the first time it is actually
accessed, via `importlib.import_module`, then writes the resolved value straight into
`sys.modules["aiforge"].__dict__`:

```python
def _getattr(name: str) -> object:
    module_name, attr_name = mapping[name]
    module = importlib.import_module(module_name)
    value = getattr(module, attr_name)
    sys.modules[package].__dict__[name] = value
    return value
```

so every subsequent access to `aiforge.AIForge` (or any other lazy name) is a plain attribute
lookup, not a repeated import. `import aiforge` on its own therefore only ever executes
`aiforge/__about__.py` (a single `__version__` string) and `aiforge/utils/lazy.py`
(stdlib-only: `importlib`, `sys`, `collections.abc`). Nothing under `aiforge.core`,
`aiforge.providers`, `aiforge.config`, or `aiforge.skills` runs until the caller actually touches
`aiforge.AIForge`, `aiforge.Engine`, or another lazy attribute.

The naive baseline — defined identically in `scripts/measure_startup.py` and
`benchmarks/bench_startup.py` — is what the same package would cost without that trick:

```python
_NAIVE_BASELINE_CODE = (
    "from aiforge.core.engine import Engine\n"
    "from aiforge.api.client import AIForge\n"
    "from aiforge.providers.registry import ProviderRegistry\n"
    "from aiforge.skills.loader import discover_skills\n"
    "discover_skills()\n"
)
```

`aiforge.core.engine` alone pulls in `AIForgeConfig`, `TaskContext`/`TaskRequest`, `EventBus`,
`CostTracker`, `ProviderRegistry`, `ProviderRouter`, the shared `providers.types` module, and the
full skill subsystem (`discover_skills`, `SkillRegistry`, `SkillResolver`); `aiforge.api.client`
adds the config loader and `bounded_gather` on top. The explicit `discover_skills()` call then does
real I/O: it opens and parses all 10 built-in `skill.toml` files under
`src/aiforge/skills/builtin/` with `tomllib`, validates required fields, builds 10 frozen
`SkillManifest` instances, and scans installed-package entry points in the `aiforge.skills` group
(`importlib.metadata.entry_points`). None of that work happens on the lazy path unless the caller
actually asks for a provider or resolves a skill. (Even this "naive" baseline stops short of
importing the `anthropic` SDK itself — `AnthropicProvider.__init__` defers `import anthropic` to
construction time, so that cost is excluded from both sides of this particular comparison.)

### `scripts/measure_startup.py` — 5 subprocess runs, averaged

| | mean import time | min | peak RSS (mean) |
|---|---|---|---|
| optimized (lazy `import aiforge`) | 9.9 ms | 9.1 ms | 11.2 MiB |
| naive baseline (eager engine+providers+skills import) | 88.0 ms | 83.2 ms | 23.0 MiB |

**~8.9x faster, ~2.1x less peak memory.** Each run spawns a fresh `python -c "..."` subprocess
(`sys.executable`, fixed argv, no untrusted input) and reads
`resource.getrusage(resource.RUSAGE_SELF).ru_maxrss` right after the import. The script's own
comment notes `ru_maxrss` is reported in KiB on Linux but bytes on macOS — it assumes Linux, the
project's documented dev/CI platform, which is also the platform these numbers were measured on.

### `bench_startup.py` — pytest-benchmark cross-check

| | mean |
|---|---|
| optimized (lazy) | 23.5 ms |
| naive baseline | 117.2 ms |

**~5.0x faster** — same direction, different absolute numbers, because pytest-benchmark's
calibration adds its own per-round subprocess-spawn overhead on top of the import itself. Treat
`measure_startup.py`'s numbers above as "AIForge import cost"; treat this table as confirmation
that the result isn't an artifact of one particular measurement method.

## Caching

`aiforge.utils.cache` provides `TTLCache` (an `OrderedDict`-backed, thread-safe, LRU-evicting cache
with an optional per-entry TTL) and a `@cached(maxsize=..., ttl=...)` decorator built on top of it:

```python
def cached(*, maxsize: int = 128, ttl: float | None = None):
    def decorator(func):
        cache: TTLCache[tuple[object, ...], R] = TTLCache(maxsize=maxsize, ttl=ttl)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))
            cached_value = cache.get(key)
            if cached_value is not None:
                return cached_value
            result = func(*args, **kwargs)
            cache.set(key, result)
            return result

        wrapper.cache = cache
        return wrapper
    return decorator
```

`TTLCache.get` does one dict lookup, one monotonic-clock comparison against the entry's expiry (if
any), and an `OrderedDict.move_to_end` to keep LRU order — all under a `threading.Lock`. That is the
entire cost of a hit.

`bench_cache.py` measures this against a deliberately expensive function, called 20 times per
round with the same argument (a stable value requested repeatedly — the realistic memoization
case, where after the first-ever miss every later call is a hit):

```python
def _expensive(n: int) -> int:
    global _calls
    _calls += 1
    return sum(i * i for i in range(n))

@cached(maxsize=256, ttl=60.0)
def _expensive_cached(n: int) -> int:
    return _expensive(n)

# uncached:  benchmark(lambda: [_expensive(500) for _ in range(20)])
# cached:    benchmark(lambda: [_expensive_cached(500) for _ in range(20)])
```

| | mean per round (20 calls) |
|---|---|
| uncached | 291.6 µs |
| cached (steady-state hits) | 14.0 µs |

**~20.8x faster** once warm — the uncached path re-runs `sum(i * i for i in range(500))` (a Python
loop of 500 multiply-adds) on all 20 calls every round; the cached path pays that once, then
answers the remaining calls with a dict lookup. `test_cache_hit_avoids_recomputation` asserts the
underlying function (`_calls`) only actually runs once across 50 calls to the cached wrapper, which
is what makes this an apples-to-apples "same key, repeated" comparison rather than a cache that
never gets used.

Memory overhead was measured with `tracemalloc`, filling a 1000-entry `TTLCache` with small string
values (`f"value-{i}"`) and diffing traced memory before/after:

```python
tracemalloc.start()
baseline_current, _ = tracemalloc.get_traced_memory()
cache: TTLCache[int, str] = TTLCache(maxsize=1000, ttl=60.0)
for i in range(1000):
    cache.set(i, f"value-{i}")
current, _peak = tracemalloc.get_traced_memory()
per_entry_bytes = (current - baseline_current) / 1000
```

**~246 bytes/entry** for 1000 small string entries — the `(value, expires_at)` tuple, the
`OrderedDict` node overhead, and the key itself.

## Serialization

`aiforge.utils.serialization` auto-detects `orjson` at import time and exposes `dumps` / `loads`
that use it when available, falling back to stdlib `json` with zero required dependencies:

```python
try:
    import orjson as _orjson_mod
except ImportError:
    _orjson_mod = None

HAS_ORJSON = _orjson_mod is not None

def dumps(obj: Any, *, sort_keys: bool = False) -> str:
    if _orjson_mod is not None:
        option = _orjson_mod.OPT_SORT_KEYS if sort_keys else 0
        return _orjson_mod.dumps(obj, option=option).decode("utf-8")
    return json.dumps(obj, sort_keys=sort_keys, separators=(",", ":"))

def loads(data: str | bytes) -> Any:
    if _orjson_mod is not None:
        return _orjson_mod.loads(data)
    return json.loads(data)
```

`orjson` is a compiled extension with its own encode/decode loop, rather than stdlib `json`'s
pure-Python one, and `dumps` skips a redundant encode round trip by taking `orjson`'s `bytes`
output and decoding once (there's also a `dumps_bytes` that skips even that decode, for callers
that want raw bytes). `bench_serialization.py` benchmarks both against a representative
provider-response payload:

```python
_PAYLOAD = {
    "text": "This is a representative provider response payload. " * 20,
    "model": "claude-opus-4-8",
    "provider": "anthropic",
    "usage": {"input_tokens": 512, "output_tokens": 1024, "total_tokens": 1536},
    "cost_usd": 0.0421,
    "stop_reason": "end_turn",
    "metadata": {"skills": ["python", "sql"], "retries": 0},
}
```

With `orjson` installed (the `fast` extra: `orjson>=3.10.0`, `pip install aiforge[fast]`):

| | mean `dumps` | mean `loads` |
|---|---|---|
| aiforge (orjson-accelerated) | 0.69 µs | 1.30 µs |
| stdlib `json` | 5.45 µs | 3.42 µs |

**~7.9x faster serializing, ~2.6x faster deserializing.** `test_reports_whether_orjson_is_active`
prints `HAS_ORJSON` alongside the run so the benchmark output records which path was actually
exercised.

Without the `fast` extra installed, `_orjson_mod` is `None` and `dumps`/`loads` are simply calling
stdlib `json.dumps`/`json.loads` — there is no wrapper overhead of aiforge's own on that path, so
the fallback costs exactly what plain `json` costs, no more.

## Skill discovery and resolution

### Cold discovery

`discover_skills()` (`src/aiforge/skills/loader.py`) scans `BUILTIN_SKILLS_DIR`
(`src/aiforge/skills/builtin/`) for immediate subdirectories containing a `skill.toml`, parses each
with `tomllib` via `SkillManifest.from_toml`, and appends any `aiforge.skills` entry-point-provided
manifests:

```python
def discover_skills(*, extra_dirs: Iterable[Path | str] = ()) -> list[SkillManifest]:
    manifests: list[SkillManifest] = []
    for directory in (BUILTIN_SKILLS_DIR, *(Path(d) for d in extra_dirs)):
        manifests.extend(_scan_directory(directory))
    manifests.extend(_discover_entry_points())
    return manifests
```

Cold (first-call, no cache involved) `discover_skills()` over the 10 built-in skills (`bash`,
`cpp`, `go`, `htmlcss`, `java`, `javascript`, `python`, `rust`, `sql`, `typescript`):
**~8.96 ms (~0.9 ms/skill)** — file opens, TOML parsing, and required-field validation for each
manifest. This runs once per `discover_skills()` call (typically once at engine/registry
construction), not once per resolution.

### Indexed vs. naive resolution

`SkillRegistry` indexes every registered skill's languages, frameworks, keywords, and name into an
`InvertedIndex` (`src/aiforge/utils/indexing.py`) — a `dict[token, set[item_id]]`:

```python
def register(self, manifest: SkillManifest, *, replace: bool = False) -> None:
    self._registry.register(manifest.name, manifest, replace=replace)
    tokens = (*manifest.languages, *manifest.frameworks, *manifest.keywords, manifest.name)
    self._index.add(manifest.name, tokens)

def candidates(self, tokens: list[str]) -> list[SkillManifest]:
    """Return enabled skills indexed under any of *tokens*, via the inverted index."""
    ids = self._index.query(tokens)
    ...
```

`InvertedIndex.query` is a union over per-token buckets — one dict lookup per prompt token,
regardless of how many skills are registered in total:

```python
def query(self, tokens: Iterable[str]) -> set[str]:
    """Return the union of item ids indexed under any of *tokens*."""
    result: set[str] = set()
    for token in tokens:
        result |= self._index.get(_normalize(token), set())
    return result
```

`SkillResolver._score_and_select` (`src/aiforge/skills/resolver.py`) only ever calls `_score()` on
manifests that `candidates()` already returned:

```python
def _score_and_select(self, *, prompt, file_hints):
    tokens = _tokenize(prompt)
    candidates = list(self._registry.candidates(tokens)) if tokens else []
    ...
    scored = [(score, manifest) for manifest in candidates if (score := self._score(...)) > 0]
```

so the amount of scoring work is bounded by *how many skills share a token with the prompt*, not
by *how many skills are registered*. `bench_skill_loading.py`'s naive baseline, implemented locally
in the benchmark for a like-for-like comparison, does the opposite: it computes the full weighted
score for every manifest `discover_skills()` returned, regardless of whether it has any token in
common with the prompt. `test_indexed_and_naive_resolution_agree_on_top_match` asserts both
approaches pick the same top skill for the same prompt, which is what makes the timing comparison
meaningful — it's the same scoring logic done two ways, not two different algorithms.

| | mean |
|---|---|
| indexed (`SkillResolver`, `InvertedIndex`-backed) | 18.97 µs |
| naive linear scan (rescans every registered skill) | 19.51 µs |

**Honest finding: negligible difference at only 10 registered skills** — both are comfortably
sub-20µs, and a prompt like `"Write a Python function using FastAPI and pytest that queries SQL."`
already shares a token with most of the 10 built-in skills, so "skills that match" and "skills that
exist" are nearly the same set at this scale; the index has little to prune. The index's actual
benefit is asymptotic — **O(matching tokens) instead of O(registered skills)** — and only shows up
once a project registers substantially more skills via the `aiforge.skills` entry-point plugin
mechanism, at which point most registered skills won't share a token with any given prompt and the
naive baseline keeps scoring all of them anyway. This benchmark is not evidence of a large win
today; it's evidence the two algorithms agree, at a scale too small to show the difference the
index is designed for.

## Reproducing these numbers

```bash
pip install -e ".[dev,fast]"
pytest benchmarks/ --benchmark-only               # bench_*.py, via pytest-benchmark
python scripts/measure_startup.py                 # standalone time + memory report
python scripts/repo_size_report.py                # tracked repo size, once committed
```

Or run one benchmark file at a time, as each file's own docstring documents:

```bash
pytest benchmarks/bench_startup.py --benchmark-only
pytest benchmarks/bench_cache.py --benchmark-only
pytest benchmarks/bench_serialization.py --benchmark-only
pytest benchmarks/bench_skill_loading.py --benchmark-only
```

`pyproject.toml`'s `[tool.pytest.ini_options]` sets `python_files = ["test_*.py", "bench_*.py"]`,
which is what lets pytest (and pytest-benchmark) collect `bench_*.py` files at all, but
`testpaths = ["tests"]` keeps a bare `pytest` invocation scoped to `tests/` — `benchmarks/` is only
collected when you point pytest at it explicitly, so it never slows down or affects the regular
test run.

Numbers depend on the machine and Python build they're measured on; these were produced on Python
3.11.15, Linux, with `orjson` installed. Without the `fast` extra, the two "optimized" rows in the
serialization table collapse to the stdlib `json` numbers, since `aiforge.utils.serialization`
transparently falls back — there's nothing to install to reproduce that half of the comparison.

## See also

- [../README.md](../README.md) — project overview and quickstart
- [architecture.md](architecture.md) — layering, dependency injection, extensibility contracts
- [providers.md](providers.md) — Claude setup, adding a new provider, routing
- [api.md](api.md) — `AIForge` facade, CLI, HTTP server
- [plugin-development.md](plugin-development.md) — adding a provider without touching core
- [skill-creation.md](skill-creation.md) — the `skill.toml` schema and authoring workflow
- [repo-optimization.md](repo-optimization.md) — why the repo stays small
