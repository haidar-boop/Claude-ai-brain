# Architecture

AIForge is built around two seams: a provider seam (`Provider` protocol) and a skill seam
(`skill.toml` manifests). Every layer between the facade and those seams is plain constructor
injection over small, single-purpose types, so each layer is independently unit-testable and new
providers/skills are pure additions -- registration, not edits to `core/`. This document walks the
layering, the two extensibility contracts, how dependency injection is actually used (as opposed
to the optional `Container` utility), the step-by-step request flow, the error hierarchy, and the
design principles the codebase holds itself to.

## Layers

```
                              CLI / HTTP / Python facade
        aiforge.api.cli:main   aiforge.server.app:serve   aiforge.api.client.AIForge
                                          │
                                          │  Engine.run() / .arun() / .stream() / .astream()
                                          ▼
                             Engine   (aiforge.core.engine)
                             ├── EventBus        (aiforge.core.events)
                             └── CostTracker     (aiforge.providers.cost)
                             ╱                                        ╲
             ProviderRouter                                    SkillResolver
          (aiforge.providers.router)                        (aiforge.skills.resolver)
          rules -> fallback -> retry                         score -> select -> compose
                    │                                                    │
                    ▼                                                    ▼
            ProviderRegistry                                      SkillRegistry
       (aiforge.providers.registry)                          (aiforge.skills.registry)
        .discover_entry_points()                        .register_all(discover_skills())
                    │                                                    │
                    ▼                                                    ▼
      AnthropicProvider, FakeProvider, ...                 SkillManifest x N (skill.toml)
      (lazy `anthropic` import,                          builtin/ dir + extra_dirs +
       retry, cost tracking)                              aiforge.skills entry points
                                          ▲
                                          │  Engine.from_config(config)
             Config: defaults.toml < aiforge.toml < AIFORGE__SECTION__KEY env vars
             aiforge.config.loader.load_config() -> aiforge.config.schema.AIForgeConfig

  ─────────────────────────────────────────────────────────────────────────────────
   aiforge.utils -- shared foundation layer; everything above depends downward into
   it (directly or transitively), nothing in it depends back upward
   cache.TTLCache   serialization.dumps/loads   async_utils.bounded_gather
   lazy.lazy_getattr / lazy_dir   indexing.InvertedIndex   logging.get_logger
  ─────────────────────────────────────────────────────────────────────────────────
```

- **Facade** (`aiforge/api/`, `aiforge/server/`) -- three thin entry points over one engine:
  `aiforge.api.cli:main` (argparse; each subcommand handler imports its dependencies lazily, so
  `aiforge --version` never imports the engine), `aiforge.server.app:serve` (a dependency-free
  `http.server.ThreadingHTTPServer` exposing `POST /run` and `GET /health`), and
  `aiforge.api.client.AIForge`, the Python facade both of the above build on. `AIForge.__init__`
  calls `load_config()` then `Engine.from_config(self.config)`.
- **Engine** (`aiforge.core.engine.Engine`) -- the framework's single integration point. It is the
  only class that imports from both the provider layer and the skill layer; neither of those
  layers imports the other or imports `Engine`.
- **ProviderRouter / SkillResolver** -- per-request policy. The router applies routing rules,
  fallback order, and retry around provider selection; the resolver scores, selects, and composes
  skill guidance. Neither knows the other exists.
- **ProviderRegistry / SkillRegistry** -- discovery and lookup. Thin domain wrappers around the
  generic `aiforge.core.registry.Registry[T]` name-to-item store, adding typed not-found errors
  (`ProviderNotFoundError`, `SkillNotFoundError`) and discovery logic (`discover_entry_points()`,
  directory scan) that `Registry[T]` itself knows nothing about.
- **Concrete providers / skill manifests** -- `AnthropicProvider` and `FakeProvider` implement the
  `Provider` protocol; `SkillManifest` instances are parsed from `skill.toml` files or built by
  entry-point code.
- **Config** feeds `Engine.from_config()` but does not reach further down than that call: it
  configures *which* default provider, routing rules, fallback order, retry attempts, and skill
  enable/disable policy are used to build the router and registries. `AIForgeConfig.providers`
  (per-provider `model` / `max_tokens` / `max_retries` / `timeout` / `extra`, looked up via
  `AIForgeConfig.provider_config(name)`) is part of the schema and is populated from
  `[providers.<name>]` sections, but `Engine.from_config()` does not thread it into provider
  construction -- providers are instantiated through their bare, zero-argument entry-point
  factory (`ProviderRegistry.get_or_create(name)` with no kwargs), so a provider's effective model
  comes from that provider class's own default unless a `RoutingRule.model` or `TaskRequest.model`
  pins one explicitly. A caller that wants config-driven provider construction builds the instance
  itself and registers it via `ProviderRegistry.register_factory()`, or calls
  `ProviderRegistry.get_or_create(name, **kwargs)` directly.
- **`aiforge.utils`** is the dependency-free foundation every other package sits on: `cache.py`
  (`TTLCache`, `@cached`), `serialization.py` (`dumps`/`dumps_bytes`/`loads`, orjson-accelerated
  when installed), `async_utils.py` (`bounded_gather`), `lazy.py` (`lazy_getattr`/`lazy_dir`, the
  PEP 562 machinery behind `aiforge/__init__.py`), `indexing.py` (`InvertedIndex`, backing
  `SkillRegistry.candidates()`), and `logging.py` (`get_logger`).

## Extending without touching core

### Providers: entry points or manual registration

`ProviderRegistry` (`aiforge/providers/registry.py`) discovers factories two ways, and both are
pure additions -- neither touches `core/`, `engine.py`, or any other provider:

```python
_ENTRY_POINT_GROUP = "aiforge.providers"

def discover_entry_points(self) -> None:
    """Register every provider factory advertised via the entry-point group.

    Safe to call multiple times; an already-registered name is left
    alone (call :meth:`register_factory` with ``replace=True`` to
    override explicitly).
    """
    for entry_point in entry_points(group=_ENTRY_POINT_GROUP):
        if entry_point.name in self._factories:
            continue
        self._factories.register(entry_point.name, entry_point.load())
```

AIForge's own two providers are registered this way, in `pyproject.toml`:

```toml
[project.entry-points."aiforge.providers"]
anthropic = "aiforge.providers.anthropic_provider:AnthropicProvider"
fake = "aiforge.providers.fake:FakeProvider"
```

A third-party package ships an equivalent `[project.entry-points."aiforge.providers"]` section
pointing at its own class -- no dependency on `aiforge` at import time beyond the `Provider`
protocol it implements. Or, at runtime, skip entry points entirely:

```python
registry.register_factory("my-provider", MyProvider, replace=False)
```

`register_factory(name, factory, *, replace=False)` accepts any keyword-args-only callable
returning a `Provider`; the provider class itself is typically its own factory, since every
built-in provider's `__init__` takes only keyword arguments.

### Skills: directory scan or entry points

`discover_skills()` (`aiforge/skills/loader.py`) is the single function `Engine.from_config()`
calls to assemble the full skill set:

```python
BUILTIN_SKILLS_DIR = Path(__file__).parent / "builtin"
_ENTRY_POINT_GROUP = "aiforge.skills"
_MANIFEST_FILENAME = "skill.toml"

def discover_skills(*, extra_dirs: Iterable[Path | str] = ()) -> list[SkillManifest]:
    manifests: list[SkillManifest] = []
    for directory in (BUILTIN_SKILLS_DIR, *(Path(d) for d in extra_dirs)):
        manifests.extend(_scan_directory(directory))
    manifests.extend(_discover_entry_points())
    return manifests
```

Three sources, all merged:

1. **`BUILTIN_SKILLS_DIR`** -- `src/aiforge/skills/builtin/`, one subdirectory per skill
   (`bash/`, `cpp/`, `go/`, `htmlcss/`, `java/`, `javascript/`, `python/`, `rust/`, `sql/`,
   `typescript/`), each containing a `skill.toml`.
2. **`extra_dirs`** -- additional directories configured via `[skills] extra_dirs = [...]` in
   `aiforge.toml` (`SkillsConfig.extra_dirs`), scanned the same way as the built-in directory.
3. **The `aiforge.skills` entry-point group** -- for skills shipped as installable packages
   (e.g. closed-source or org-specific skills) rather than a TOML file in this repo.

Both directory sources go through `_scan_directory()`, which only looks at *immediate*
subdirectories containing a `skill.toml` and parses each with `SkillManifest.from_toml()`.
Entry points go through `_discover_entry_points()`:

```python
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

An entry point may resolve to a `SkillManifest` instance directly, or to a zero-argument callable
that builds one -- for skill packages that construct their manifest in Python instead of shipping
a TOML file. Either way, adding a skill never means editing `SkillRegistry`, `SkillResolver`, or
`Engine`. See [`skill-creation.md`](skill-creation.md) for the `skill.toml` schema itself and
[`plugin-development.md`](plugin-development.md) for the provider side in more depth.

## Dependency injection

Every collaborator in the request path is passed into its owner's constructor -- nothing looks
itself up from a module-level global or a singleton. `tests/unit/test_core_engine.py` builds a
fully working engine this way, with zero network access and zero API key:

```python
registry = ProviderRegistry()
registry.register_factory("fake", lambda: FakeProvider(model="fake-model"))
router = ProviderRouter(registry, default_provider="fake", max_attempts=1)
skill_registry = SkillRegistry()
engine = Engine(router=router, skill_resolver=SkillResolver(skill_registry))
```

The same pattern repeats at every layer:

- `Engine(*, router: ProviderRouter, skill_resolver: SkillResolver, cost_tracker: CostTracker | None = None, events: EventBus | None = None, base_system: str | None = None)`
- `ProviderRouter(registry: ProviderRegistry, *, default_provider: str, rules: tuple[RoutingRule, ...] = (), fallback_order: tuple[str, ...] = (), max_attempts: int = 2, retry_base_delay: float = 1.0, retry_sleep: Callable[[float], None] = time.sleep)`
- `SkillResolver(registry: SkillRegistry, *, max_skills: int = 3)`

`Engine` depends on the `Provider` *protocol* (via `ProviderRouter` -> `ProviderRegistry`), never
on `AnthropicProvider` or the `anthropic` SDK -- which is exactly what lets `FakeProvider` stand in
everywhere in tests, examples, and CI: it satisfies `aiforge.providers.base.Provider` (a
`@runtime_checkable Protocol`), so `ProviderRegistry`, `ProviderRouter`, and `Engine` cannot tell
it apart from `AnthropicProvider`. `retry_sleep` is itself injected (defaulting to `time.sleep`)
so retry-and-fallback tests don't burn real wall-clock time.

### `Container`/`Key[T]`: an optional typed service locator, not the wiring mechanism

`aiforge.core.container.Container` and `aiforge.core.container.Key[T]` (`core/container.py`) are a
separate, opt-in facility -- a minimal generic registry of factories keyed by a typed `Key[T]`
token, with optional singleton caching:

```python
from aiforge.core.container import Container, Key

router_key: Key[ProviderRouter] = Key("router")
container = Container()
container.register(router_key, lambda: ProviderRouter(registry, default_provider="anthropic"))
router = container.resolve(router_key)  # built on first use; cached (singleton=True by default)
```

This is **distinct** from the constructor injection used throughout the framework itself:
`Engine.__init__` has no `Container` parameter, `Engine.from_config()` builds every collaborator
with plain constructor calls, and nothing in `core/`, `providers/`, or `skills/` resolves its own
dependencies from a `Container`. It exists for callers *built on top of* AIForge who want dynamic,
token-keyed wiring -- e.g. assembling several differently-configured engines at runtime -- without
hand-threading every constructor argument themselves. Two `Key` instances are never equal even
with the same label; identity, not the label string, is what `Container` keys on, so accidental
collisions between unrelated registrations aren't possible.

## Request flow

`Engine.run(request: TaskRequest) -> EngineResult` (`aiforge/core/engine.py`):

1. **`self._prepare(request)`**:
   - Resolves skills via `self.skill_resolver.resolve(explicit=request.skills, prompt=request.prompt, file_hints=request.file_hints)`.
     - If `request.skills` is non-empty, each name is looked up with `SkillRegistry.require()`
       (raises `SkillNotFoundError` if unknown), filtered to `manifest.enabled`, and capped at
       `max_skills` (default 3).
     - Otherwise `SkillResolver._score_and_select()` tokenizes the prompt, pulls candidates from
       `SkillRegistry.candidates()` (an `InvertedIndex` lookup, not a linear scan), adds any
       enabled skill whose `file_globs` match `request.file_hints`, scores each candidate
       (`3x` per matched language, `2x` per matched framework/library, `1x` per matched keyword,
       `+4` for a file-glob match), sorts by `(-score, -priority, name)`, and takes the top
       `max_skills`.
   - Composes the system prompt: `_compose_system(self.base_system, request.system, resolved.composed_guidance)`
     joins whichever of those three are non-empty with a blank line; each selected skill
     contributes a `## <name> skill` section via `SkillManifest.prompt_guidance()`.
   - Builds a `build_request(model) -> ChatRequest` closure: a single `Message(role=Role.USER,
     content=request.prompt)`, `max_tokens=request.max_tokens or 4096`, the composed `system`, and
     `stream=request.stream`.
2. **`self.events.emit("engine.request_started", skills=[m.name for m in resolved.selected])`**
   publishes an `Event` on the `EventBus` (synchronous, in-process; handlers run in subscription
   order).
3. **`self.router.call(build_request, provider=request.provider, model=request.model, hint=request.prompt)`**:
   - `ProviderRouter.select()`: an explicit `provider` argument wins outright; otherwise the first
     `RoutingRule` whose `match` substring is found in `hint.lower()` wins, contributing its
     `provider`/`model`; otherwise `default_provider` (no model override).
   - Builds the fallback chain: `[provider_name, *(p for p in fallback_order if p != provider_name)]`.
   - For each candidate name in the chain: `ProviderRegistry.require()` it (on
     `ProviderNotFoundError`, remember it as `last_error` and try the next candidate);
     `effective_model = model_override or candidate.model`; build the request; call
     `candidate.complete()` wrapped in `retry_with_backoff()`, which retries only
     `ProviderRateLimitError`/`ProviderTimeoutError` (`_TRANSIENT_ERRORS`), up to `max_attempts`
     times, with exponential backoff (`base_delay * 2**attempt`, capped at 30s) plus up to 25%
     jitter.
   - Any other `ProviderError`, or exhausting retries, moves to the next candidate in the chain;
     the first candidate to succeed returns immediately. If the whole chain fails, the last error
     seen is re-raised.
   - Returns `RoutedResponse(response, provider_name)`, where `provider_name` is the *registry
     alias* that actually served the request -- not necessarily equal to `response.provider` (the
     provider implementation's own fixed identity, e.g. `"anthropic"`), since two aliases can wrap
     the same implementation class under different names.
4. **`self._track_cost(routed.response)`**: `CostTracker.record(model, usage)` looks the model up
   in `aiforge.providers.cost.PRICING`; an unpriced model returns `None` and the response passes
   through unchanged, otherwise the running totals are updated and the response gets
   `cost_usd` filled in via `dataclasses.replace`.
5. Builds `TaskContext(request=request, provider_name=routed.provider_name, model=response.model, resolved_skills=tuple(m.name for m in resolved.selected), composed_system=system)`.
6. **`self.events.emit("engine.request_completed", provider=routed.provider_name, model=response.model)`**.
7. Returns `EngineResult(response=response, context=context)`.

`arun()` is `await asyncio.to_thread(self.run, request)` -- it exists so async callers don't block
their event loop, not because the pipeline above is natively async (only
`AnthropicProvider.acomplete`/`.astream` use the `anthropic` SDK's real async client).

### Streaming bypasses router retry/fallback -- deliberately

`Engine.stream()` and `.astream()` call `_prepare_streaming()` (the same skill resolution and
system composition as `run()`, via `_prepare()`), then `self.router.select()` -- **not**
`.call()` -- to pick a `(provider_name, model)` pair with no retry and no fallback chain. They
fetch the provider directly (`self.router.registry.require(provider_name)`), fill in the resolved
model with `dataclasses.replace`, and iterate `provider.stream()` / `provider.astream()`,
recording cost only off the trailing chunk (`chunk.is_final and chunk.usage is not None`). The
engine's own docstring states why:

> Unlike `run()`, streaming does not retry or fall back: once output has started reaching the
> caller, silently restarting on a different provider would produce a corrupted or duplicated
> stream.

`run()` can safely retry or fall back to a different provider because nothing has reached the
caller yet by the time a retry happens; `stream()`/`astream()` hand chunks to the caller as they
arrive, so there is no safe point after the first chunk to discard and restart from.

## Error hierarchy

Every exception in AIForge inherits from `AIForgeError` (`aiforge/core/errors.py`):

```
AIForgeError
├── ConfigError
│   └── ConfigValidationError
├── RegistryError
├── EngineError
├── ProviderError
│   ├── ProviderNotFoundError    (also RegistryError)
│   ├── ProviderAuthError
│   ├── ProviderRateLimitError   (carries retry_after: float | None)
│   ├── ProviderTimeoutError
│   └── ProviderResponseError
└── SkillError
    ├── SkillNotFoundError       (also RegistryError)
    ├── SkillValidationError     (carries source: str | None)
    └── SkillConflictError       (carries skills: tuple[str, ...])
```

`ProviderNotFoundError` and `SkillNotFoundError` each inherit from both their own domain base
*and* `RegistryError`, so `except RegistryError` catches either "not found" error without also
catching an unrelated domain error such as a rate limit or a manifest validation failure.

## Design principles

- **SOLID.**
  - *SRP*: `aiforge.core.registry.Registry[T]` is the bare name-to-item primitive; `ProviderRegistry`
    and `SkillRegistry` each layer their own not-found error and discovery logic on top of it
    rather than folding that logic into it.
  - *OCP*: new providers and skills are added by registering (entry points, `register_factory()`,
    a new `skill.toml`), never by editing `Engine`, `ProviderRouter`, or `SkillResolver` -- see
    "Extending without touching core" above.
  - *LSP*: anything satisfying the `Provider` protocol is substitutable everywhere the engine
    expects one; `FakeProvider` and `AnthropicProvider` are interchangeable in `ProviderRegistry`,
    `ProviderRouter`, and `Engine` without any of them special-casing either.
  - *ISP*: `Provider` exposes exactly five methods (`complete`, `stream`, `acomplete`, `astream`,
    `count_tokens`) -- nothing an implementation doesn't need to supply. `BaseProvider` (the
    shared `ABC`) only defaults `acomplete` (via `asyncio.to_thread`); every other method stays
    abstract because there's no safe generic way to turn a sync streaming generator into a real
    async one.
  - *DIP*: `Engine` and `ProviderRouter` depend on the `Provider` protocol and on
    `ProviderRegistry`/`SkillRegistry`, never on `anthropic` or a concrete provider class. The only
    module that imports `anthropic` is `providers/anthropic_provider.py`, and even there the
    import happens inside `__init__`, not at module scope.
- **Strong typing.** `mypy --strict` (`[tool.mypy] strict = true`, plus `warn_unused_ignores` and
  `warn_redundant_casts`, in `pyproject.toml`) covers `src/`. Most data types are
  `@dataclass(frozen=True, slots=True)`. Generic containers (`Registry[T]`, `Container`/`Key[T]`)
  preserve static types through `resolve`/`get`/`require` instead of erasing to `object` at call
  sites -- `core/container.py` documents exactly which lines need a narrow `# type: ignore` for
  that erasure-at-storage-time trick, and why each one is safe.
- **Zero required runtime dependencies.** `dependencies = []` in `pyproject.toml`; `anthropic` and
  `orjson` are optional extras (`aiforge[anthropic]`, `aiforge[fast]`), each imported lazily (see
  below), so a plain `pip install aiforge` still gives a fully working framework against
  `FakeProvider` with the standard-library `json` module as the serialization fallback.
- **Lazy loading throughout.** `aiforge/__init__.py` uses PEP 562 (`__getattr__`/`__dir__` built by
  `aiforge.utils.lazy.lazy_getattr`/`lazy_dir`) so `import aiforge` does not import the engine,
  any provider SDK, or the skill system until an attribute is actually touched, and each name is
  imported at most once. `AnthropicProvider.__init__` imports `anthropic` inside the method body
  so merely enumerating providers (`aiforge providers list`) never requires the extra to be
  installed. `api/cli.py` subcommand handlers import their dependencies inside each handler
  function for the same reason -- `aiforge --version` touches none of it.

## See also

- [README](../README.md)
- [AI Provider Integration Guide](providers.md)
- [API Reference](api.md)
- [Plugin Development Guide](plugin-development.md)
- [Skill Creation Guide](skill-creation.md)
- [Performance Report](performance.md)
- [Repository Optimization Guide](repo-optimization.md)
