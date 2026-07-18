# AIForge

A modular, provider-agnostic AI coding framework: a clean provider abstraction over Claude (and
any future LLM), and a plugin-based **skill system** that lets you teach the framework a new
programming language or coding capability by dropping in a folder — no core code changes.

[![CI](https://github.com/haidar-boop/claude-ai-brain/actions/workflows/ci.yml/badge.svg)](https://github.com/haidar-boop/claude-ai-brain/actions/workflows/ci.yml)
[![Lint](https://github.com/haidar-boop/claude-ai-brain/actions/workflows/lint.yml/badge.svg)](https://github.com/haidar-boop/claude-ai-brain/actions/workflows/lint.yml)
[![CodeQL](https://github.com/haidar-boop/claude-ai-brain/actions/workflows/codeql.yml/badge.svg)](https://github.com/haidar-boop/claude-ai-brain/actions/workflows/codeql.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)

## Why AIForge

Most "AI framework" starting points either hardcode a single provider deep inside business logic,
or bolt on new capabilities by editing a growing `if language == ...` block. AIForge is built
around two boundaries instead:

- **Provider layer** — the engine talks to a `Provider` protocol, never to an SDK directly.
  Switching from Claude to a second provider, or routing different tasks to different models, is a
  config change, not a code change.
- **Skill system** — a "skill" is a declarative manifest (`skill.toml`) describing a language or
  framework's patterns, best practices, debugging strategy, and review rules. The framework
  discovers skills from a directory or from installed packages' entry points, scores them against
  the current task, resolves conflicts, and composes the winners into guidance for the model. Add
  a `skill.toml` for Elixir tomorrow; nothing in `src/aiforge` changes.

Ships with a **zero-cost `FakeProvider`** for local development and CI — you can run every example
and the entire test suite without an API key or a single dollar spent.

## Features

- **AI provider abstraction** — unified `complete` / `stream` / async variants; automatic retry,
  timeout, and rate-limit handling (via the underlying SDK); token usage and cost tracking;
  request/response debug logging with secrets redacted; multiple providers can coexist with
  rule-based routing.
- **Claude support out of the box** — `AnthropicProvider` wraps the official `anthropic` SDK, reads
  `ANTHROPIC_API_KEY` from the environment (never hardcoded, never accepted via config), and
  defaults to `claude-opus-4-8`.
- **Plugin skill system** — auto-discovery, compatibility validation, enable/disable via config,
  multi-skill composition, and priority-based conflict resolution. Ten example skills included:
  Python, JavaScript, TypeScript, Rust, Go, C++, Java, SQL, HTML/CSS, Bash.
- **Performance-engineered** — PEP 562 lazy public API, lazy SDK imports, LRU+TTL response and
  manifest caching, an inverted index for skill lookup, async/bounded-concurrency helpers,
  `__slots__` on hot-path types, optional `orjson` acceleration. See
  [`docs/performance.md`](docs/performance.md) for methodology and measured numbers.
- **Small footprint** — zero required runtime dependencies, `src/` layout, skills expressed as
  TOML data rather than code, aggressive `.gitignore`, no generated files committed. See
  [`docs/repo-optimization.md`](docs/repo-optimization.md).
- **Production-ready tooling** — typed strictly (mypy `--strict`), linted (ruff), scanned (bandit +
  CodeQL), tested (pytest, unit + integration, no network required), benchmarked
  (pytest-benchmark + memory profiling), and wired into GitHub Actions.

## Architecture

```
                         CLI / HTTP / Python facade   (aiforge.api, aiforge.server)
                                       │
                          Engine (aiforge.core.engine)
                          ├── EventBus            (aiforge.core.events)
                          └── Container (DI)       (aiforge.core.container)
                          ╱                          ╲
          ProviderRouter                         SkillResolver
       (aiforge.providers.router)          (aiforge.skills.resolver)
                │                                     │
        ProviderRegistry                       SkillRegistry ◄── SkillLoader
   (aiforge.providers.registry)          (aiforge.skills.registry)  (entry points + directory scan)
                │
        AnthropicProvider, FakeProvider, ...
     (lazy SDK import, retry, cost tracking)
                                       │
        Config (defaults.toml < aiforge.toml < env)      Utils (cache, serialize, async, lazy, index)
```

Every box above is independently unit-testable and constructor-injected — the `Engine` doesn't
import `AnthropicProvider` or any particular skill; it depends only on the `Provider` protocol and
the skill registry interface. See [`docs/architecture.md`](docs/architecture.md) for the full
design rationale.

## Quickstart

```bash
pip install -e ".[dev,anthropic,fast]"
```

### Zero-cost: run against the built-in FakeProvider (no API key, no network)

```bash
python examples/quickstart.py
```

This exercises the full path — config loading, skill resolution, engine orchestration, cost
tracking — against `aiforge.providers.fake.FakeProvider`, so you can develop, test, and demo the
framework without spending anything.

### Real Claude

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # see .env.example
```

```python
from aiforge import AIForge

forge = AIForge()  # loads aiforge.toml if present, else sensible defaults
response = forge.run("Write a Python function that reverses a linked list.")
print(response.text)
print(f"cost: ${response.cost_usd:.4f}  tokens: {response.usage.total_tokens}")
```

Or via the CLI:

```bash
aiforge run "Write a Python function that reverses a linked list." --skill python
aiforge skills list
aiforge providers list
aiforge config show
```

## Configuration

AIForge loads configuration in layers, each overriding the last:
`src/aiforge/config/defaults.toml` → `aiforge.toml` (project root or `$AIFORGE_CONFIG`) →
environment variables (`AIFORGE__SECTION__KEY=value`). Example `aiforge.toml`:

```toml
[engine]
default_provider = "anthropic"

[providers.anthropic]
model = "claude-opus-4-8"
max_tokens = 4096

[skills]
enabled = ["python", "typescript", "sql"]

[routing]
# Route anything mentioning Rust to a different model tier, fall back to default.
rules = [{ match = "rust", provider = "anthropic", model = "claude-opus-4-8" }]
```

API keys are **never** read from this file — only from environment variables — so
`aiforge.toml` is always safe to commit.

## Repository layout

```
src/aiforge/    core/ providers/ skills/ config/ api/ server/ utils/
tests/          unit/ integration/
examples/       quickstart.py streaming.py multi_provider_routing.py custom_skill/
benchmarks/     bench_startup.py bench_cache.py bench_serialization.py bench_skill_loading.py
docs/           architecture.md providers.md api.md plugin-development.md skill-creation.md
                performance.md repo-optimization.md
scripts/        repo_size_report.py measure_startup.py
```

## Documentation

- [Architecture](docs/architecture.md) — layering, dependency injection, extensibility contracts
- [AI Provider Integration Guide](docs/providers.md) — Claude setup, adding a new provider, routing
- [API Reference](docs/api.md) — `AIForge` facade, CLI, HTTP server
- [Plugin Development Guide](docs/plugin-development.md) — adding a provider without touching core
- [Skill Creation Guide](docs/skill-creation.md) — the `skill.toml` schema and authoring workflow
- [Performance Report](docs/performance.md) — benchmark methodology and measured results
- [Repository Optimization Guide](docs/repo-optimization.md) — why the repo stays small

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). New language support or provider integrations are
welcome as pure additions — a new `skill.toml` folder or a new `providers/*.py` file — that
require no edits to existing core files.

## License

[MIT](LICENSE)
