# Repository Optimization Guide

AIForge treats repository size and clone weight as something to design for, not clean up after
the fact. This guide covers the concrete practices that keep the tree small — a single build
configuration, zero required runtime dependencies, skills expressed as data instead of code, an
aggressive `.gitignore`, no committed generated output, and no Git LFS — and how to measure the
current numbers yourself. It's the storage counterpart to [performance.md](performance.md), which
covers runtime cost instead.

## One `src/` tree, one build file

The whole framework builds from a single root `pyproject.toml` using the `hatchling` backend:

```toml
[build-system]
requires = ["hatchling>=1.25"]
build-backend = "hatchling.build"
```

Source lives under a `src/` layout (`src/aiforge/`, not a flat package at the repo root), and the
wheel target is scoped explicitly:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/aiforge"]

[tool.hatch.build]
include = [
  "src/aiforge/**/*.py",
  "src/aiforge/**/*.toml",
  "src/aiforge/py.typed",
]
```

`include` here is an allowlist, not a denylist — only `.py` source, `.toml` skill/config data, and
the `py.typed` marker are packaged into the wheel. A stray generated file that somehow ended up
under `src/aiforge/` (a cache artifact, an accidental copy) simply wouldn't be picked up by the
build; nothing has to remember to exclude it after the fact.

There is exactly one `pyproject.toml` governing the framework, and no `setup.py`, `setup.cfg`, or
`requirements*.txt` anywhere in the repository — dependencies, entry points, and every tool's
configuration (`ruff`, `mypy`, `pytest`, `coverage`, `bandit`) live in that single file.

The one other `pyproject.toml` in the repository, `examples/custom_skill/pyproject.toml`, is
deliberate rather than scatter: it's a minimal, self-contained example package
(`aiforge-skill-elixir`) demonstrating how an *out-of-tree* skill is packaged and registered via
the `aiforge.skills` entry-point group —

```toml
[project.entry-points."aiforge.skills"]
elixir = "aiforge_skill_elixir:load_manifest"
```

— meant to be copied as a starting point for a real out-of-tree package, not built as part of
`aiforge` itself. See [plugin-development.md](plugin-development.md) for the full mechanism.

## Zero required runtime dependencies

```toml
[project]
dependencies = []
```

The engine, provider routing, skill resolution, layered config loading, the CLI, and the stdlib
HTTP server all run on nothing but the Python 3.11+ standard library:

| Concern | Stdlib module | Where |
|---|---|---|
| TOML parsing (config + skill manifests) | `tomllib` | `aiforge/config/loader.py`, `aiforge/skills/manifest.py` |
| CLI argument parsing | `argparse` | `aiforge/api/cli.py` |
| HTTP JSON server | `http.server` (`BaseHTTPRequestHandler`, `ThreadingHTTPServer`) | `aiforge/server/app.py` |
| Provider/skill plugin discovery | `importlib.metadata` (`entry_points`) | `aiforge/providers/registry.py`, `aiforge/skills/loader.py` |

`pip install aiforge` with no extras pulls in zero third-party packages, and every one of those
subsystems imports and runs.

Three optional extras opt into more, listed here exactly as declared in
`[project.optional-dependencies]`:

```toml
[project.optional-dependencies]
anthropic = ["anthropic>=0.40.0"]
fast = ["orjson>=3.10.0"]
dev = [
  "pytest>=8.3",
  "pytest-asyncio>=0.24",
  "pytest-cov>=5.0",
  "pytest-benchmark>=4.0",
  "ruff>=0.6.9",
  "mypy>=1.11",
  "bandit[toml]>=1.7.10",
  "pre-commit>=3.8",
]
```

- **`anthropic`** — the official Claude SDK, needed only to use `AnthropicProvider`.
- **`fast`** — `orjson`, an accelerated JSON encoder/decoder.
- **`dev`** — test runner, coverage, benchmarking, linting, type checking, and pre-commit hooks.

Both `anthropic` and `orjson` are imported lazily and guarded rather than at module top level, so
the dependency stays optional in practice, not just on paper. `AnthropicProvider` imports
`anthropic` inside its own `__init__`, and turns a missing package into an actionable error instead
of an import-time crash:

```python
# src/aiforge/providers/anthropic_provider.py
def __init__(self, ...) -> None:
    try:
        import anthropic
    except ImportError as exc:
        raise ImportError(
            "the 'anthropic' package is required to use AnthropicProvider; "
            "install it with `pip install aiforge[anthropic]`"
        ) from exc
```

`aiforge.utils.serialization` imports `orjson` once at module load, also guarded, and transparently
falls back to the stdlib `json` module when it isn't installed:

```python
# src/aiforge/utils/serialization.py
try:
    import orjson as _orjson_mod
except ImportError:
    _orjson_mod = None  # type: ignore[assignment]

HAS_ORJSON = _orjson_mod is not None
```

Neither import failing breaks anything outside the code path that actually needs it — the rest of
the framework, including its test suite, doesn't notice either extra is missing.

## Skills are data, not code

Each of the ten built-in skills is a single `skill.toml` manifest under
`src/aiforge/skills/builtin/<name>/` — nothing else lives in those directories:

```
src/aiforge/skills/builtin/
├── bash/skill.toml
├── cpp/skill.toml
├── go/skill.toml
├── htmlcss/skill.toml
├── java/skill.toml
├── javascript/skill.toml
├── python/skill.toml
├── rust/skill.toml
├── sql/skill.toml
└── typescript/skill.toml
```

No `.py` files, no vendored parser or linter integration, no per-language package. Each manifest is
plain structured text: a `name` and `description`, `languages` / `frameworks` / `libraries` /
`file_globs` match criteria, `keywords`, flat string lists (`patterns`, `best_practices`,
`debugging`, `optimization`, `testing`, `review_rules`), a `documentation_style` string, and a
`requires` list for skill-to-skill dependencies. From `python/skill.toml`:

```toml
name = "python"
description = "Python language, ecosystem, and idiomatic patterns for scripting, web backends, and data work."
languages = ["python"]
frameworks = ["Django", "FastAPI", "Flask", "pytest", "SQLAlchemy", "Celery"]
file_globs = ["*.py", "*.pyi", "pyproject.toml", "requirements*.txt", "Pipfile"]
```

These files are small: each of the ten built-in manifests measures roughly 7-10 KB of TOML, and all
ten together total under 90 KB. Adding language number eleven — Elixir, Kotlin, whatever — costs
one more small text file, either in-tree under `builtin/` or out-of-tree as an installable package
registered under the `aiforge.skills` entry point (exactly what `examples/custom_skill/`
demonstrates). It never costs a vendored code module, a duplicated boilerplate package, or a
core-file edit. See [skill-creation.md](skill-creation.md) for the full manifest schema.

## `.gitignore`: what's excluded

`.gitignore` at the repo root keeps generated and machine-local files out of every commit, grouped
by category:

- **Byte-compiled / cache** — `__pycache__/`, `*.py[cod]`, `*$py.class`, `*.so`
- **Distribution / packaging** — `build/`, `dist/`, `*.egg-info/`, `.eggs/`, `wheels/`
- **Virtual environments** — `.venv/`, `venv/`, `env/`, `ENV/`
- **Secrets / environment** — `.env`, `.env.*`, with `!.env.example` explicitly un-ignoring the
  committed template so the example ships but a real key never can
- **Test / coverage / type-check artifacts** — `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`,
  `.coverage`, `.coverage.*`, `htmlcov/`, `coverage.xml`, `*.cover`, `.hypothesis/`, `.tox/`,
  `.nox/`, `.benchmarks/`, `benchmarks/results/`
- **Editors / OS** — `.idea/`, `.vscode/`, `*.swp`, `.DS_Store`, `Thumbs.db`
- **Logs** — `*.log`
- **Node** — `node_modules/` (the `custom_skill` examples may pull in JS tooling; it's never
  committed)

## No generated files are ever committed

Coverage reports, benchmark output, bytecode caches, and build artifacts are all covered by the
categories above and never make it into a commit. This isn't just policy — running the local dev
loop actually produces these directories on disk:

```bash
pytest --cov=aiforge --cov-report=term-missing   # writes .coverage
pytest benchmarks --benchmark-only               # writes .benchmarks/
mypy src                                          # writes .mypy_cache/
ruff check .                                      # writes .ruff_cache/
```

`git status` never shows them, because each one resolves to a `.gitignore` rule (verifiable with
`git check-ignore -v <path>`) rather than sitting there as an untracked file waiting to be added by
mistake. `[tool.coverage.report]` sets `fail_under = 90`, so coverage is strictly enforced on every
CI run — but the report itself is regenerated every time and never checked in. The same `include`
allowlist described above means that even if a generated file somehow landed under `src/aiforge/`,
it still wouldn't ship in the built wheel unless it happened to end in `.py` or `.toml`.

## No Git LFS

AIForge does not use Git LFS, deliberately. Every tracked file in the repository is source text —
Python, TOML, Markdown, YAML (GitHub Actions workflows, pre-commit config) — plus a couple of small
plain-text config files like `LICENSE` and `.env.example`. There is no vendored dataset, no model
weights, no images, no audio/video fixtures — nothing binary or large enough to strain plain Git.

LFS isn't free to adopt: it means a separate storage backend, a clone-time dependency (contributors
need `git-lfs` installed and the smudge filter configured, or they get pointer stubs instead of
real files), and extra CI setup to fetch LFS objects before anything can run. Paying that cost when
nothing in the repository needs it would be complexity for its own sake.

That's a description of the current repository, not a permanent rule. Git LFS would be worth
revisiting if the project later started vendoring things plain Git handles poorly, for example:

- large fixture repositories or sample projects checked in for integration tests,
- audio/video/image test media for a skill that deals with those formats,
- binary model artifacts (e.g., local embedding or classifier weights bundled instead of downloaded
  at runtime).

If and when a change like that is proposed, evaluate LFS against what's actually being added at
that point. Until then, it stays out.

## Checking tracked size yourself

`scripts/repo_size_report.py` measures the repository the way GitHub actually bills and clones it:
by what's tracked, not by what happens to be sitting in the working directory. It shells out to
`git ls-files` — fixed argv, no untrusted input — rather than walking the filesystem with something
like `os.walk` or `Path.rglob`, which would also pick up `.gitignore`d caches, virtual
environments, and build output that were never going to be part of a clone in the first place:

```python
def _tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"], check=True, capture_output=True, text=True, timeout=30
    )
    return [Path(line) for line in result.stdout.splitlines() if line]
```

For every tracked file it `stat()`s the size on disk and prints:

- `Tracked files: <count>` and `Total tracked size: <KiB>`
- **By top-level directory** — size summed per first path component, largest first (root-level
  files such as `README.md` or `pyproject.toml` are grouped under `.`)
- **By extension** — size summed per suffix, largest first (extensionless files such as `LICENSE`
  are grouped under `(no extension)`)
- **Files over 50 KB** (`_LARGE_FILE_THRESHOLD_BYTES = 50_000` bytes) — listed largest first as
  candidates for manual review, or a one-line note that nothing crosses the threshold if the
  repository is clean

Run it with no arguments and no dependencies beyond the standard library (`subprocess`, `pathlib`,
`collections.defaultdict`):

```bash
python scripts/repo_size_report.py
```

A note on numbers: this documentation set is being authored and landed commit by commit alongside
the rest of the framework, so any specific KiB figure written into prose here would be stale within
a commit or two — this file alone adds a few more KB the moment it's committed. Rather than freeze
a snapshot that goes wrong almost immediately, this guide deliberately doesn't hardcode one. Run
the script above for the real, current breakdown; expect this section to be revisited with a
concrete worked example once the initial build-out settles.

## See also

- [../README.md](../README.md) — project overview and quickstart
- [architecture.md](architecture.md) — layering, dependency injection, extensibility contracts
- [providers.md](providers.md) — Claude setup, adding a new provider, routing
- [api.md](api.md) — `AIForge` facade, CLI, HTTP server
- [plugin-development.md](plugin-development.md) — adding a provider without touching core
- [skill-creation.md](skill-creation.md) — the `skill.toml` schema and authoring workflow
- [performance.md](performance.md) — benchmark methodology and measured results
