# Contributing to AIForge

## Development setup

```bash
git clone <repo-url>
cd claude-ai-brain
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,anthropic,fast]"
pre-commit install
```

Everything below runs with **no API key and no network access** — the test suite, examples, and
benchmarks all use `aiforge.providers.fake.FakeProvider`. You only need `ANTHROPIC_API_KEY` for
the tests marked `@pytest.mark.live` (skipped by default) or for manual testing against real
Claude.

## Running checks locally

```bash
ruff check .                 # lint
ruff format --check .        # formatting
mypy src                     # strict type checking
pytest                       # unit + integration tests
pytest --cov=aiforge --cov-report=term-missing   # with coverage
bandit -c pyproject.toml -r .                    # security scan (skips tests/benchmarks)
pytest benchmarks --benchmark-only               # performance benchmarks
```

`pre-commit run --all-files` runs the lint/format/type-check subset of the above as a single
command; CI runs the full set (see `.github/workflows/`).

## Adding a provider

New providers are pure additions — see [`docs/plugin-development.md`](docs/plugin-development.md).
In short: implement the `Provider` protocol in a new `src/aiforge/providers/<name>.py`, register it
under the `aiforge.providers` entry-point group (in-tree) or in a separate installable package
(out-of-tree), and it's available via `aiforge.toml` without any change to `core/` or `engine.py`.

## Adding a skill

New languages/frameworks are pure additions — see
[`docs/skill-creation.md`](docs/skill-creation.md). Create a directory with a `skill.toml`
manifest under `src/aiforge/skills/builtin/` (in-tree) or ship it as an installable package
registered under the `aiforge.skills` entry-point group (out-of-tree, e.g. for closed-source or
organization-specific skills). No core file needs to change.

## Code style

- Strong typing everywhere; `mypy --strict` must pass with no `# type: ignore` unless justified
  with a comment.
- No comments explaining *what* code does — name things well instead. Comments are reserved for
  non-obvious *why* (a workaround, an invariant, a subtle constraint).
- Keep functions focused; prefer composition over large branching functions.
- Every public module should be importable and testable on its own — avoid hidden global state.

## Commit messages

Use imperative mood ("Add Rust skill", not "Added Rust skill"). Reference the module touched when
useful (`providers: add retry jitter`, `skills: fix conflict resolution tie-break`).

## Pull requests

- Keep PRs scoped to one concern.
- Add or update tests for behavior changes.
- Run the full check list above before requesting review.
- Update `CHANGELOG.md` under "Unreleased" for user-visible changes.
