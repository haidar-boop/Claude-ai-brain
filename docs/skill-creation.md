# Skill Creation Guide

A skill is a declarative bundle of language/framework knowledge — coding patterns, best
practices, debugging and optimization strategies, a testing approach, review rules, documentation
style — that the engine composes into its system prompt when a task matches it. Skills are pure
data (`skill.toml`, parsed into a `SkillManifest`), not code: adding one never means editing
`SkillRegistry`, `SkillResolver`, or `Engine`.

This document is about *skills*. AIForge's other plugin mechanism, the **provider layer** (the
thing that talks to an LLM API), is a separate extension point with its own entry-point group and
contract — see [`plugin-development.md`](plugin-development.md) instead. Nothing below applies to
providers, and nothing there applies to skills.

## 1. The `skill.toml` schema

Every skill is one `skill.toml` file, parsed and validated into a `SkillManifest`
(`src/aiforge/skills/manifest.py`), a frozen, slotted dataclass:

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `name` | `str` | *required* | The id the skill is registered, requested (`--skill python`), and referenced (`requires = [...]`) under. |
| `description` | `str` | *required* | One-line summary; the second line of `prompt_guidance()`'s rendered output. |
| `languages` | `tuple[str, ...]` | `()` | Language names. Indexed for automatic matching, worth 3 points per hit. |
| `frameworks` | `tuple[str, ...]` | `()` | Framework names. Indexed, worth 2 points per hit. |
| `libraries` | `tuple[str, ...]` | `()` | Library names. Worth 2 points per hit once a skill is a candidate — **not indexed** (§2). |
| `file_globs` | `tuple[str, ...]` | `()` | `fnmatch` patterns (e.g. `"*.py"`, `"pyproject.toml"`) matched against file hints; any hit is a flat 4 points. |
| `keywords` | `tuple[str, ...]` | `()` | Free-form trigger words. Indexed, worth 1 point per hit. |
| `patterns` | `tuple[str, ...]` | `()` | Idiomatic patterns to suggest — rendered as a "Coding patterns" section. |
| `best_practices` | `tuple[str, ...]` | `()` | Rendered as "Best practices". |
| `debugging` | `tuple[str, ...]` | `()` | Rendered as "Debugging strategies". |
| `optimization` | `tuple[str, ...]` | `()` | Rendered as "Optimization strategies". |
| `testing` | `tuple[str, ...]` | `()` | Rendered as "Testing approach". |
| `review_rules` | `tuple[str, ...]` | `()` | Rendered as "Code review rules". |
| `documentation_style` | `str` | `""` | Rendered as "Documentation style" — a single string, not a list. |
| `requires` | `tuple[str, ...]` | `()` | Names of other skills this one composes with or depends on (documentation only — see §2). |
| `priority` | `int` | `0` | Conflict-resolution tie-breaker: higher wins when two skills score equally (§2). |
| `enabled` | `bool` | `True` | Default enabled state, overridable per-deployment by `[skills]` config (§5). |

A 16th attribute, `source: str = ""`, exists on the dataclass but is **not** part of the
`skill.toml` schema — `SkillManifest.from_toml`/`from_dict` stamp it with the file path or
entry-point name for diagnostics. Putting `source = "..."` in your `skill.toml` fails validation
exactly like any other unrecognized key.

`keywords` and `requires` are used for resolution/documentation only — they do **not** appear in
`prompt_guidance()`'s rendered output. Only `languages`, `frameworks`, `libraries`, `patterns`,
`best_practices`, `debugging`, `optimization`, `testing`, `review_rules`, and
`documentation_style` are rendered into the composed guidance text sent to the model.

### Validation

`SkillManifest.from_dict` — and `from_toml`, which parses the file then delegates to it — is
strict:

- `name` and `description` are required. A missing or falsy value raises `SkillValidationError`
  naming the missing field(s).
- Every other top-level key must be one of the fields above. **Unknown fields raise
  `SkillValidationError`** (`f"unknown field {key!r}"`) — there is no lenient "ignore what I don't
  recognize" fallback, so a typo like `bestpractices` (missing the underscore) fails loudly at load
  time instead of silently doing nothing.
- The twelve list-shaped fields (`languages`, `frameworks`, `libraries`, `file_globs`, `keywords`,
  `patterns`, `best_practices`, `debugging`, `optimization`, `testing`, `review_rules`, `requires`)
  must be TOML arrays — `languages = "python"` (a bare string) raises `SkillValidationError`
  rather than being auto-wrapped into a one-element tuple.
- `priority` is coerced with `int(...)`, `enabled` with `bool(...)`; `name`, `description`, and
  `documentation_style` are coerced with `str(...)`.
- Invalid TOML syntax and unreadable files also raise `SkillValidationError` (wrapping the
  underlying `tomllib.TOMLDecodeError` / `OSError`), so every manifest-loading failure surfaces as
  the same exception type.

### Minimal example

```toml
name = "elixir"
description = "Elixir language, OTP concurrency model, and the Phoenix web framework."
```

This is complete and valid — every other field defaults to empty. It is also not automatically
discoverable: with no `languages`/`frameworks`/`keywords`/`file_globs`, this skill scores `0` for
every task (§2) and can only ever be selected explicitly (`--skill elixir`). Give a real skill at
least `languages` or `keywords`.

### Full example: `builtin/python/skill.toml`

`src/aiforge/skills/builtin/python/skill.toml` is the reference to copy from. Its header and the
four fields used for matching, verbatim:

```toml
name = "python"
description = "Python language, ecosystem, and idiomatic patterns for scripting, web backends, and data work."

languages = ["python"]

frameworks = ["Django", "FastAPI", "Flask", "pytest", "SQLAlchemy", "Celery"]

libraries = ["requests", "numpy", "pandas", "pydantic", "httpx", "click"]

file_globs = ["*.py", "*.pyi", "pyproject.toml", "requirements*.txt", "Pipfile"]

keywords = ["python", "pip", "venv", "django", "flask", "fastapi", "pandas", "numpy", "pytest"]
```

It goes on to declare 10 entries each in `patterns`, `best_practices`, `debugging`,
`optimization`, and `testing`, plus 10 `review_rules`, a `documentation_style` string, and
`requires = []`. One entry from each, verbatim, to show the expected level of specificity:

```toml
patterns = [
    "Use context managers (the with statement, or @contextlib.contextmanager) for resource management instead of manual try/finally acquire-release pairs",
    # ... 9 more
]

review_rules = [
    "Flag mutable default arguments such as def f(x=[]): the default is created once and shared across calls; require None with in-function initialization",
    # ... 9 more
]

documentation_style = "Write PEP 257-compliant docstrings on every public module, class, and function: a concise imperative one-line summary, followed by a blank line and a structured Args/Returns/Raises section (Google or NumPy style) for anything with parameters or non-trivial behavior."

requires = []
```

Read the full file for the rest. Every entry names a real API or a concrete, checkable rule ("Flag
`== None`", not "handle nulls carefully") — that specificity is what makes `prompt_guidance()`'s
output useful system-prompt content rather than generic advice.

## 2. How resolution and scoring works

`SkillResolver` (`src/aiforge/skills/resolver.py`) turns a `SkillRegistry` full of manifests plus a
task — prompt text, optional file hints, optional explicit skill names — into the skills actually
used:

```python
class SkillResolver:
    def __init__(self, registry: SkillRegistry, *, max_skills: int = 3) -> None: ...

    def resolve(
        self, *, explicit: tuple[str, ...] = (), prompt: str = "", file_hints: tuple[str, ...] = ()
    ) -> ResolvedSkills: ...


@dataclass(frozen=True, slots=True)
class ResolvedSkills:
    selected: tuple[SkillManifest, ...]
    composed_guidance: str | None
```

`Engine` calls this as `skill_resolver.resolve(explicit=request.skills, prompt=request.prompt,
file_hints=request.file_hints)` — `TaskRequest.skills`/`.file_hints` are exactly what
`AIForge.run(prompt, skills=[...], file_hints=[...])` and the CLI's repeatable `--skill` flag
populate.

### Explicit skills always win

If `explicit` is non-empty, scoring never runs:

```python
if explicit:
    requested = [self._registry.require(name) for name in explicit]
    selected = [m for m in requested if m.enabled][: self.max_skills]
```

- **Order is preserved** — skills come back in the order you named them, not re-sorted.
- **Unknown names raise `SkillNotFoundError`** immediately — `SkillRegistry.require` wraps a
  `KeyError` into it, listing the names that *are* available.
- **Disabled skills are silently dropped, not errored** — `explicit=("rust", "cobol")` with `rust`
  disabled via config returns just `("cobol",)`, no exception
  (`test_resolve_explicit_skips_disabled_without_raising`).
- The result is still capped at `max_skills` (constructor arg, default 3), applied *after* the
  disabled filter, preserving your requested order.

### Automatic scoring

With no explicit names, `_score_and_select` runs:

1. **Tokenize the prompt.** `_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+#._-]*")` matches runs
   starting with a letter and continuing with letters, digits, `+`, `#`, `.`, `_`, or `-` — so
   `"Next.js"`, `"c++"`, and `"c#"` each tokenize as one whole token.
2. **Gather candidates.** `registry.candidates(tokens)` queries an `InvertedIndex`
   (`src/aiforge/utils/indexing.py`) built at registration time from each manifest's
   `languages + frameworks + keywords + name` (`SkillRegistry.register`) — **not** `libraries`,
   `file_globs`, or any guidance field. Separately, any enabled manifest not already a candidate is
   added if a file hint matches one of its `file_globs`.
3. **Score each candidate**, verbatim:

   ```python
   def _score(
       self, manifest: SkillManifest, tokens: list[str], file_hints: tuple[str, ...]
   ) -> int:
       token_set = {t.lower() for t in tokens}
       score = 0
       score += 3 * len(token_set & {v.lower() for v in manifest.languages})
       score += 2 * len(token_set & {v.lower() for v in manifest.frameworks})
       score += 2 * len(token_set & {v.lower() for v in manifest.libraries})
       score += 1 * len(token_set & {v.lower() for v in manifest.keywords})
       if _matches_any_glob(file_hints, manifest.file_globs):
           score += 4
       return score
   ```

   Matching is case-insensitive but whole-token (both sides are lowercased before intersecting),
   not substring or prefix matching. Only candidates scoring `> 0` survive.
4. **Sort and truncate.** `scored.sort(key=lambda pair: (-pair[0], -pair[1].priority,
   pair[1].name))` — highest score wins; `priority` breaks score ties (higher wins); `name` breaks
   any remaining tie alphabetically. The top `max_skills` survive.
5. **Compose.** `composed_guidance = "\n\n".join(m.prompt_guidance() for m in selected)`, or `None`
   if nothing scored above 0.

#### Worked example

The shipped `javascript` and `typescript` skills both list `"React"` as a framework. For the
prompt `"Fix this React bug"` (tokens `{fix, this, react, bug}`):

| Skill | `frameworks` hit | `keywords` hit | Score |
| --- | --- | --- | --- |
| `javascript` | `React` -> +2 | `react` -> +1 | **3** |
| `typescript` | `React` -> +2 | *(none)* | **2** |

`javascript` outranks `typescript` here specifically because `javascript`'s `keywords` list
includes `"react"` and `typescript`'s (`["typescript", "ts", "tsx", "interface", "generic",
"type-safe"]`) doesn't. That's the practical lesson for authoring `keywords`: because `libraries`
and `file_globs` are not indexed, a skill only becomes a *candidate* through a `languages` /
`frameworks` / `keywords` / `name` token match, or a file hint. If you want a prompt that mentions
only a library name — no accompanying language/framework word, no file hint — to still surface
your skill, list that library's name in `keywords` too, not only in `libraries`.

#### Priority as the tie-break

None of AIForge's 10 built-in skills sets `priority` above its default of `0`, so ties among them
resolve alphabetically today. The resolver's own tests are the clearest illustration of what
`priority` is for
(`tests/unit/test_skills_resolver.py::test_resolve_conflict_resolution_uses_priority_tiebreak`):
two manifests both declaring `languages=("shared",)`, scoring identically, with `priority=1` and
`priority=5` — the `priority=5` manifest wins. Reach for `priority` only when a skill specifically
needs to outrank an equally-scored competitor.

#### `requires` documents intent; nothing enforces it yet

`requires` is validated like any other list field, but no code in `SkillResolver`,
`SkillRegistry`, or `SkillManifest` reads it back — there is no automatic dependency expansion, no
"pull in the skills this one requires," no check that the named skills even exist. Today it is
purely documentation of composition intent inside the manifest itself. If a skill's guidance
genuinely depends on another skill's guidance also being present, request both explicitly
(`--skill python --skill sql`) or make sure both score highly enough to be selected together.

A hard, unresolvable conflict between two *enabled* skills is a distinct concept from a *scoring*
tie: `SkillConflictError` (`src/aiforge/core/errors.py`, carries `skills: tuple[str, ...]`) exists
in AIForge's error hierarchy for that case, but nothing in the current resolver raises it — every
scoring tie resolves deterministically via `priority`/`name` as described above, never by
erroring.

### Inspecting resolution

```bash
aiforge skills show python                                   # prints prompt_guidance() for one skill
aiforge run "fix this django bug" --skill python --skill sql # force specific skills, order preserved
```

## 3. Shipping a skill in-tree

`discover_skills()` (`src/aiforge/skills/loader.py`) always scans
`BUILTIN_SKILLS_DIR = Path(__file__).parent / "builtin"` — i.e. `src/aiforge/skills/builtin/` —
in addition to any configured `extra_dirs` and installed entry points:

```python
def discover_skills(*, extra_dirs: Iterable[Path | str] = ()) -> list[SkillManifest]:
    manifests: list[SkillManifest] = []
    for directory in (BUILTIN_SKILLS_DIR, *(Path(d) for d in extra_dirs)):
        manifests.extend(_scan_directory(directory))
    manifests.extend(_discover_entry_points())
    return manifests
```

`_scan_directory` walks a directory's **immediate** subdirectories (sorted) and parses
`skill.toml` from every one that has it. This is exactly how this repo's own 10 built-in skills
work:

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

Each directory holds nothing but `skill.toml` — no `__init__.py`, not a Python package. The
directory name matching the manifest's `name` field is a convention this repo follows consistently
(all 10 do), not something `_scan_directory` checks — it never reads the directory name, only
`name` inside the TOML.

To add one: create `src/aiforge/skills/builtin/<name>/skill.toml` per the schema in §1. That is
the entire change — no import to add, no registration call to make, nothing else in `src/aiforge`
touched. It's picked up the next time anything builds a registry (`Engine.from_config`, `aiforge
skills list`, a direct `discover_skills()` call). Confirm with:

```bash
aiforge skills list --all
```

Use this path for a skill you want bundled with AIForge itself, shipped with every install,
maintained alongside the framework's own tests and CI. For anything else — a niche or internal
language, a closed-source skill, one you'd rather version and release independently — use §4.

## 4. Shipping a skill out-of-tree (recommended for most new skills)

A separate installable package is the better default for most new skills, including third-party
ones: it's versioned independently of AIForge's own releases, needs no PR against this repo, and
is discovered identically to a built-in skill once installed. The mechanism is the
`aiforge.skills` entry-point group, discovered by this function:

```python
_ENTRY_POINT_GROUP = "aiforge.skills"

def _discover_entry_points() -> list[SkillManifest]:
    manifests = []
    for entry_point in entry_points(group=_ENTRY_POINT_GROUP):
        loaded = entry_point.load()
        manifest = loaded() if callable(loaded) else loaded
        if not isinstance(manifest, SkillManifest):
            raise TypeError(
                f"entry point {entry_point.name!r} in group {_ENTRY_POINT_GROUP!r} must "
                f"resolve to a SkillManifest, got {type(manifest).__name__}"
            )
        manifests.append(manifest)
    return manifests
```

An entry point may resolve to a zero-argument callable that returns a `SkillManifest`, or to a
`SkillManifest` instance directly (used as-is, since `callable()` is `False` for a plain dataclass
instance). The demonstrated, recommended pattern — used by every example in this repo — is a
zero-arg function that parses a bundled `skill.toml` via `SkillManifest.from_toml`.

### Worked example: `examples/custom_skill/`

A complete, real, installable package in this repo that adds an "elixir" skill with zero changes
to `src/aiforge`:

```
examples/custom_skill/
├── pyproject.toml
└── src/
    └── aiforge_skill_elixir/
        ├── __init__.py
        └── skill.toml
```

`pyproject.toml` declares the package and registers `load_manifest` under `aiforge.skills`:

```toml
[project]
name = "aiforge-skill-elixir"
version = "0.1.0"
description = "Example out-of-tree AIForge skill: Elixir."
requires-python = ">=3.11"
dependencies = ["aiforge"]

[project.entry-points."aiforge.skills"]
elixir = "aiforge_skill_elixir:load_manifest"
```

`src/aiforge_skill_elixir/__init__.py` is the entire implementation:

```python
from pathlib import Path
from aiforge.skills.manifest import SkillManifest

__all__ = ["load_manifest"]

_MANIFEST_PATH = Path(__file__).parent / "skill.toml"


def load_manifest() -> SkillManifest:
    """Entry-point target: parses and returns this package's SkillManifest."""
    return SkillManifest.from_toml(_MANIFEST_PATH)
```

`src/aiforge_skill_elixir/skill.toml` is an ordinary manifest, the same schema as §1: `name =
"elixir"`, `languages = ["elixir"]`, `frameworks = ["Phoenix", "OTP", "Ecto"]`, `file_globs =
["*.ex", "*.exs", "mix.exs"]`, `keywords = ["elixir", "phoenix", "otp", "genserver", "mix",
"erlang"]`, and on through `patterns`, `best_practices`, `debugging`, `optimization`, `testing`,
`review_rules`, `documentation_style`, and `requires = []`.

Try it — this exact sequence was verified working end to end, with no AIForge core file touched:

```bash
pip install -e examples/custom_skill
aiforge skills list --all   # "elixir" now appears
aiforge run "How do I model state in Elixir?" --skill elixir
```

Installed packages are picked up automatically the next time anything calls `discover_skills()` —
which `Engine.from_config()` (and therefore both the `AIForge` facade and the CLI) always does.
There's no separate opt-in call needed the way `ProviderRegistry.discover_entry_points()` is a
distinct step on the provider side.

### Adapting this for your own skill

Copy the three files, then:

1. Rename the package (`[project] name = "aiforge-skill-elixir"` -> `"aiforge-skill-<yours>"`) and
   the source directory (`src/aiforge_skill_elixir` -> `src/aiforge_skill_<yours>`).
2. Update the entry-point line to match: `<yours> = "aiforge_skill_<yours>:load_manifest"`.
3. Replace `skill.toml`'s contents per §1.
4. `pip install -e .` locally, or publish the package and let users `pip install
   aiforge-skill-<yours>`.

## 5. Enabling/disabling skills via config

`SkillsConfig` (`src/aiforge/config/schema.py`) is the config-level policy layer, applied on top of
whatever each manifest's own `enabled` field says:

```python
@dataclass(frozen=True, slots=True)
class SkillsConfig:
    enabled: tuple[str, ...] | None = None
    disabled: tuple[str, ...] = ()
    extra_dirs: tuple[str, ...] = ()
```

- **`enabled`** — an explicit allowlist. `None` (the default) means "leave every skill's own
  `enabled` flag as its manifest declared it." An explicit tuple restricts the whole registry to
  exactly those names; an empty tuple (`enabled = []`) means "none."
- **`disabled`** — an always-off list, applied *after* `enabled`. A name in `disabled` is off even
  if it's also in the `enabled` allowlist.
- **`extra_dirs`** — extra directories to scan for skills, beyond the built-in directory. Each
  entry is scanned exactly like `BUILTIN_SKILLS_DIR`: a *parent* directory whose immediate
  subdirectories each contain a `skill.toml`, not a path to a single manifest file directly. E.g.
  `extra_dirs = ["/opt/company-skills"]` expects `/opt/company-skills/<name>/skill.toml` per
  internal skill.

`SkillRegistry.apply_policy` implements the `enabled`/`disabled` interaction, verbatim:

```python
def apply_policy(self, *, enabled: tuple[str, ...] | None, disabled: tuple[str, ...]) -> None:
    """Apply config-driven enable/disable policy across all registered skills.

    *enabled* of ``None`` leaves each skill's own ``enabled`` flag as
    the manifest declared it; an explicit tuple restricts to exactly
    those names. Names in *disabled* are always turned off, regardless
    of *enabled*.
    """
    for name in self.names():
        manifest = self.require(name)
        is_enabled = name in enabled if enabled is not None else manifest.enabled
        if name in disabled:
            is_enabled = False
        if is_enabled != manifest.enabled:
            updated = dataclasses.replace(manifest, enabled=is_enabled)
            self._registry.register(name, updated, replace=True)
```

It's wired up in exactly one place, `Engine.from_config` — which both the `AIForge` facade and the
CLI build on:

```python
skill_registry = SkillRegistry()
skill_registry.register_all(discover_skills(extra_dirs=config.skills.extra_dirs))
skill_registry.apply_policy(enabled=config.skills.enabled, disabled=config.skills.disabled)
```

### `aiforge.toml` example

```toml
[skills]
enabled = ["python", "typescript", "sql"]   # allowlist: everything else off
disabled = ["sql"]                          # always off, even though listed in `enabled`
extra_dirs = ["/opt/company-skills"]        # scanned like builtin/: <dir>/<name>/skill.toml
```

With this config: `python` and `typescript` are enabled; `sql` is off, blocked by `disabled`
despite being allowlisted; every other built-in skill (`javascript`, `rust`, `go`, `cpp`, `java`,
`htmlcss`, `bash`) is off because it isn't in the `enabled` allowlist; anything discovered under
`/opt/company-skills/*/skill.toml` or via an installed `aiforge.skills` entry point is off too
unless it's also named in `enabled`.

The shipped defaults (`src/aiforge/config/defaults.toml`) only set the always-safe values:

```toml
[skills]
disabled = []
extra_dirs = []
```

`enabled` is left unset (`None`), so out of the box every discovered skill stays on.

### Other ways to select skills

| Interface | Effect |
| --- | --- |
| `aiforge skills list` | Lists enabled skills. |
| `aiforge skills list --all` | Lists every discovered skill, disabled ones marked `(disabled)`. |
| `aiforge skills show <name>` | Prints that skill's full `prompt_guidance()` text. |
| `aiforge run "<prompt>" --skill <name>` | Forces specific skills (repeatable flag), bypassing scoring. |
| `AIForge.run(prompt, skills=[...])` | Same, from Python (`run_detailed`/`stream`/`astream` too). |

Config layers the same way everywhere in AIForge: `src/aiforge/config/defaults.toml` <
`aiforge.toml` < `AIFORGE__SECTION__KEY` environment variables. One caveat specific to `[skills]`:
the environment-override coercer (`_coerce_env_value` in `src/aiforge/config/loader.py`) only
turns a raw string into `bool`/`int`/`float`, falling back to the string itself — it does **not**
split on commas into a list. `AIFORGE__SKILLS__DISABLED=rust` does not disable the `rust` skill; it
sets `disabled` to `tuple("rust")`, i.e. `('r', 'u', 's', 't')`, none of which match a real skill
name. Set `enabled`/`disabled`/`extra_dirs` in `aiforge.toml`, not through the environment.

## Checklist

- `name` and `description` set; every list field is a TOML array of strings, never a bare string
  where a list is expected (`documentation_style` is the one plain-string exception).
- At least one of `languages`/`frameworks`/`keywords`/`file_globs` populated, or the skill can only
  ever be reached via explicit `--skill`/`skills=[...]`.
- Library names you want to trigger the skill from prompt text alone are also listed in
  `keywords` — `libraries` itself isn't indexed.
- In-tree: `src/aiforge/skills/builtin/<name>/skill.toml`, nothing else changed. Confirm with
  `aiforge skills list --all`.
- Out-of-tree: `[project.entry-points."aiforge.skills"]` in your package's `pyproject.toml`
  pointing at a zero-arg callable returning a `SkillManifest`; `pip install -e .`; confirm the
  same way.
- If the skill should ship disabled by default for most users, set `enabled = false` in the
  manifest itself rather than relying on every consumer's `aiforge.toml` to disable it.

## See also

- [../README.md](../README.md) — project overview and quickstart
- [architecture.md](architecture.md) — layering, dependency injection, extensibility contracts
- [providers.md](providers.md) — Claude setup, the `Provider` protocol, cost tracking, routing
- [api.md](api.md) — `AIForge` facade, CLI, HTTP server
- [plugin-development.md](plugin-development.md) — adding a provider without touching core
- [performance.md](performance.md) — benchmark methodology and measured results
- [repo-optimization.md](repo-optimization.md) — why the repo stays small
