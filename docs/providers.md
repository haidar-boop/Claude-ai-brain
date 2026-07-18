# AI Provider Integration Guide

AIForge talks to language models through a single `Provider` protocol
(`src/aiforge/providers/base.py`). The engine never imports an SDK type
directly — it builds a provider-neutral `ChatRequest`, hands it to whichever
`Provider` the router selected, and gets back a provider-neutral
`ChatResponse`. This document covers configuring the built-in Claude
integration, the protocol itself, cost tracking, multi-provider routing, how
to add a new provider, and the zero-cost `FakeProvider` used by the test
suite and examples.

## 1. Setting up Claude

Copy the example env file and fill in a real key:

```bash
cp .env.example .env
```

```
# .env
ANTHROPIC_API_KEY=sk-ant-...
```

`ANTHROPIC_API_KEY` is the only thing you need to set. AIForge reads
provider credentials from the environment **only** — `AnthropicProvider`
never hardcodes a key and nothing in AIForge's config loader or CLI ever
accepts one from `aiforge.toml` or a `--flag`. The `api_key` argument on
`AnthropicProvider.__init__` exists purely for callers who want to inject a
key explicitly (e.g. from a secrets manager); when it's left as `None` (the
default, and the only path AIForge's own config/CLI layer takes), the
`anthropic.Anthropic()` / `anthropic.AsyncAnthropic()` clients built inside
`AnthropicProvider` fall back to the SDK's own credential resolution
(`ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, or an `ant auth login`
profile). AIForge does not reimplement any part of that resolution.

Optionally point the SDK at a proxy or alternate endpoint:

```
# ANTHROPIC_BASE_URL=
```

This maps to the same `base_url` constructor argument, forwarded to the SDK
client only when set.

The default model is `DEFAULT_MODEL = "claude-opus-4-8"`, defined in
`src/aiforge/providers/anthropic_provider.py` and used whenever a
`ChatRequest.model` isn't otherwise supplied.

### Config surface

`ProviderConfig` (`src/aiforge/config/schema.py`) is the typed shape of a
`[providers.<name>]` section:

```python
@dataclass(frozen=True, slots=True)
class ProviderConfig:
    model: str | None = None
    max_tokens: int = 4096
    max_retries: int = 2
    timeout: float = 600.0
    extra: dict[str, object] = field(default_factory=dict)
```

The shipped defaults (`src/aiforge/config/defaults.toml`) set:

```toml
[providers.anthropic]
model = "claude-opus-4-8"
max_tokens = 4096
max_retries = 2
timeout = 600.0
```

Override any of these in a project-root `aiforge.toml` (same shape), or via
environment variables using the `AIFORGE__<SECTION>__<KEY>` convention
(double-underscore separated, case-insensitive, values type-coerced to
bool/int/float/string automatically — see `src/aiforge/config/loader.py`):

```
AIFORGE__PROVIDERS__ANTHROPIC__MODEL=claude-opus-4-8
```

`AIForgeConfig.provider_config("anthropic")` returns this section fully
parsed and validated regardless of which layer set it (defaults, project
file, or env).

### How `[providers.<name>]` reaches the actual client

`Engine.from_config` (`src/aiforge/core/engine.py`) reads every configured
`[providers.<name>]` section and applies it to that provider's construction
via `ProviderRegistry.configure()` (`src/aiforge/providers/registry.py`),
right after `discover_entry_points()`:

```python
def _configure_providers(registry: ProviderRegistry, config: AIForgeConfig) -> None:
    for name, provider_cfg in config.providers.items():
        if name not in registry:
            continue
        candidate: dict[str, object] = {
            "max_retries": provider_cfg.max_retries,
            "timeout": provider_cfg.timeout,
            **provider_cfg.extra,
        }
        if provider_cfg.model is not None:
            candidate["model"] = provider_cfg.model
        registry.configure(name, **candidate)
```

`ProviderRegistry.configure()` only passes through the keyword arguments the
target factory's own signature actually declares (via `inspect.signature`),
or all of them if the factory accepts `**kwargs` — so the same call is safe
across providers with different constructor shapes. Setting
`[providers.anthropic] model = "claude-sonnet-5"` really does change which
model `AnthropicProvider` is built with; setting `[providers.fake]
model = "..."` for a config that routes to `FakeProvider` works the same
way, and `max_retries`/`timeout` are simply dropped for factories (like
`FakeProvider`) whose constructor doesn't declare those parameters, rather
than raising `TypeError`. Config for a provider name that isn't installed
(no matching entry point registered) is silently unused — there's nothing
to construct.

`cfg.max_tokens` is handled separately, since it has no matching
`AnthropicProvider` constructor argument — `max_tokens` is a per-request
field on `ChatRequest`, not a client setting. `Engine.from_config` reads
`config.provider_config(config.engine.default_provider).max_tokens` into
`Engine.default_max_tokens` (default `4096`), and the request builder uses
`request.max_tokens or self.default_max_tokens` — so a `[providers.<default
provider>] max_tokens = ...` setting becomes the effective default for any
request that doesn't pin its own `max_tokens` explicitly.

## 2. The `Provider` protocol and neutral types

### `Provider` (structural protocol)

```python
# src/aiforge/providers/base.py
@runtime_checkable
class Provider(Protocol):
    name: str
    model: str

    def complete(self, request: ChatRequest) -> ChatResponse: ...
    def stream(self, request: ChatRequest) -> Iterator[StreamChunk]: ...
    async def acomplete(self, request: ChatRequest) -> ChatResponse: ...
    def astream(self, request: ChatRequest) -> AsyncIterator[StreamChunk]: ...
    def count_tokens(self, request: ChatRequest) -> int: ...
```

Because it's a `@runtime_checkable typing.Protocol`, `isinstance(x, Provider)`
works structurally — a class doesn't have to inherit from anything to count
as a provider, it just has to expose `name`/`model` and the five methods
above with matching signatures.

### `BaseProvider` (ABC)

`BaseProvider` is the shared scaffolding concrete providers normally
subclass. Only `acomplete` has a concrete body:

```python
class BaseProvider(ABC):
    name: str
    model: str

    @abstractmethod
    def complete(self, request: ChatRequest) -> ChatResponse: ...

    @abstractmethod
    def stream(self, request: ChatRequest) -> Iterator[StreamChunk]: ...

    async def acomplete(self, request: ChatRequest) -> ChatResponse:
        """Default: offload the sync complete() to a thread."""
        return await asyncio.to_thread(self.complete, request)

    @abstractmethod
    def astream(self, request: ChatRequest) -> AsyncIterator[StreamChunk]: ...

    @abstractmethod
    def count_tokens(self, request: ChatRequest) -> int: ...
```

`complete`, `stream`, `astream`, and `count_tokens` are abstract — every
provider must implement them directly. `acomplete`'s thread-offload default
exists because there's no generically safe way to turn a synchronous
streaming generator into a real async one without either blocking the event
loop or building a thread+queue bridge with its own cancellation edge
cases; providers that want native async streaming implement `astream`
themselves instead (as `AnthropicProvider` and `FakeProvider` both do).

### Neutral types (`src/aiforge/providers/types.py`)

These are the contract between `aiforge.core.engine` and any `Provider`
implementation. The engine never imports an SDK type directly — each
provider translates to/from its own SDK's shapes at the boundary.

```python
class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"

@dataclass(frozen=True, slots=True)
class Message:
    role: Role
    content: str
```

```python
@dataclass(slots=True)          # the only one of these types that is *not* frozen
class ChatRequest:
    messages: tuple[Message, ...]
    model: str
    max_tokens: int = 4096
    system: str | None = None
    stream: bool = False
    temperature: float | None = None
    thinking: bool = False      # request extended/adaptive reasoning; providers
                                 # that don't support it silently ignore it
    effort: str | None = None   # e.g. "low"/"medium"/"high"/"xhigh"/"max" for Claude;
                                 # silently ignored by providers that don't support it
    extra: dict[str, Any] = field(default_factory=dict)
                                 # provider-specific passthrough, merged into the
                                 # provider's native request params last
```

```python
@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens
```

```python
@dataclass(frozen=True, slots=True)
class ChatResponse:
    text: str
    model: str
    provider: str            # the provider implementation's own fixed identity,
                              # e.g. "anthropic" -- see RoutedResponse in §5
    usage: Usage
    stop_reason: str | None = None
    cost_usd: float | None = None   # populated centrally by CostTracker via the
                                     # engine, not by the provider itself; None
                                     # means unpriced, not necessarily free
    raw: Any = None           # the provider SDK's raw response object
```

```python
@dataclass(frozen=True, slots=True)
class StreamChunk:
    text: str
    is_final: bool = False
    usage: Usage | None = None
```

A stream is zero or more chunks with `is_final=False` (incremental text,
`usage=None`), followed by exactly one trailing chunk with `is_final=True`
carrying an empty string and the completed `Usage`. Consumers that only
want the assembled text can ignore `is_final`/`usage` and just concatenate
`.text`.

## 3. How `AnthropicProvider` works

`src/aiforge/providers/anthropic_provider.py` wraps the official `anthropic`
SDK. The `anthropic` package is imported **lazily, inside `__init__`** —
not at module level:

```python
def __init__(self, *, model=DEFAULT_MODEL, api_key=None, base_url=None,
             max_retries=2, timeout=600.0) -> None:
    try:
        import anthropic
    except ImportError as exc:
        raise ImportError(
            "the 'anthropic' package is required to use AnthropicProvider; "
            "install it with `pip install aiforge[anthropic]`"
        ) from exc
    ...
```

This means `import aiforge.providers.anthropic_provider` (e.g. while
enumerating registered providers for `aiforge providers list`, or via
`ProviderRegistry.discover_entry_points()`) never requires the `anthropic`
package to be installed — only actually calling `AnthropicProvider()` pays
the SDK's import cost, and only then does a missing install surface as an
error.

On construction it builds **both** a sync and an async client from the same
kwargs:

```python
client_kwargs = {"max_retries": max_retries, "timeout": timeout}
# api_key / base_url added to client_kwargs only if explicitly passed
self._client = anthropic.Anthropic(**client_kwargs)
self._async_client = anthropic.AsyncAnthropic(**client_kwargs)
```

### Retries and timeouts

`AnthropicProvider` does not reimplement retry or timeout logic. `max_retries`
and `timeout` are passed straight through to the SDK's own `Anthropic`
/`AsyncAnthropic` clients, which already retry connection errors and
408/409/429/5xx responses with exponential backoff internally. (AIForge's
own `retry_with_backoff` helper, in `src/aiforge/providers/retry.py`, is a
separate concern — it's used by `ProviderRouter` for cross-provider
retry-then-fallback, covered in §5.)

### Request building and response parsing

`_build_params` translates a `ChatRequest` into `anthropic.messages.create`
kwargs: `model` (falls back to `self.model` if the request didn't pin one),
`max_tokens`, `messages` (each `Message` becomes `{"role": ..., "content":
...}`), optional `system`, `thinking={"type": "adaptive"}` when
`request.thinking` is set, `output_config={"effort": request.effort}` when
`request.effort` is set, optional `temperature`, and finally
`params.update(request.extra)` — so `extra` can override anything built
above.

`_to_chat_response` builds a `ChatResponse` back from the SDK's raw
`Message`: `text` is every `text`-type content block concatenated (thinking
and tool-use blocks are skipped), `usage` is read from `raw.usage`
(`cache_creation_input_tokens`/`cache_read_input_tokens` default to `0` if
the SDK response omits them), `cost_usd` is always left `None` here (cost is
computed centrally — see §4), and `raw` keeps the original SDK object for
callers that need provider-specific detail.

`complete()`, `stream()`, and `astream()` all follow the same shape: log the
request, call the SDK, translate any exception, log the outcome, return/yield.
`stream()` uses `self._client.messages.stream(...)` as a context manager;
`astream()` uses `self._async_client.messages.stream(...)` as an async
context manager. Both iterate `stream.text_stream`, yielding a `StreamChunk`
per piece, then call `stream.get_final_message()` for the completed usage
and yield the trailing `is_final=True` chunk. `count_tokens()` reuses
`_build_params` but pops `max_tokens` and `stream` (not accepted by
`messages.count_tokens`) and returns `int(result.input_tokens)`.

### Error translation

Every SDK exception raised from `complete`/`stream`/`astream` is passed
through `_translate_error` before being re-raised (`raise translated from
exc`, so the original SDK exception is always chained as the cause):

| Anthropic SDK exception | AIForge exception (`aiforge.core.errors`) | Notes |
| --- | --- | --- |
| `anthropic.AuthenticationError` | `ProviderAuthError` | missing/invalid credentials |
| `anthropic.RateLimitError` | `ProviderRateLimitError` | `retry_after` (float seconds) parsed from the response's `retry-after` header via `_parse_retry_after`; `None` if the header is missing or unparseable |
| `anthropic.APITimeoutError` | `ProviderTimeoutError` | request exceeded the client's `timeout` |
| `anthropic.APIStatusError` | `ProviderResponseError` | any other non-2xx SDK status error |
| anything else | left unchanged | re-raised as its original type |

`ProviderRateLimitError` and `ProviderTimeoutError` are the two error types
`ProviderRouter` treats as transient and retries — see §5.

## 4. Cost tracking

`src/aiforge/providers/cost.py` holds a plain, editable pricing table and a
thread-safe accumulator. `ModelPricing` is USD per 1,000,000 tokens:

```python
@dataclass(frozen=True, slots=True)
class ModelPricing:
    input_per_million: float
    output_per_million: float
    cache_write_per_million: float | None = None
    cache_read_per_million: float | None = None
```

The shipped `PRICING` table (a plain `dict[str, ModelPricing]`, explicitly
commented in source as a snapshot to **update as providers change theirs**):

| Model | Input $/1M | Output $/1M | Cache write $/1M | Cache read $/1M |
| --- | ---: | ---: | ---: | ---: |
| `claude-opus-4-8` | 5.00 | 25.00 | 6.25 | 0.50 |
| `claude-opus-4-7` | 5.00 | 25.00 | 6.25 | 0.50 |
| `claude-opus-4-6` | 5.00 | 25.00 | 6.25 | 0.50 |
| `claude-opus-4-5` | 5.00 | 25.00 | 6.25 | 0.50 |
| `claude-sonnet-5` | 3.00 | 15.00 | 3.75 | 0.30 |
| `claude-sonnet-4-6` | 3.00 | 15.00 | 3.75 | 0.30 |
| `claude-sonnet-4-5` | 3.00 | 15.00 | 3.75 | 0.30 |
| `claude-haiku-4-5` | 1.00 | 5.00 | 1.25 | 0.10 |
| `claude-fable-5` | 10.00 | 50.00 | 12.50 | 1.00 |

Cache write/read figures follow Anthropic's published multipliers (1.25x
input for a 5-minute-TTL cache write, 0.1x input for a cache read) where a
model-specific figure isn't separately published. `claude-sonnet-5` has a
temporary introductory price ($2.00/$10.00 per 1M) through 2026-08-31 per
Anthropic's pricing page; the table intentionally uses the standard
post-introductory price ($3.00/$15.00) since that's the durable value.

`estimate_cost(model, usage) -> float | None` looks up `PRICING[model]` and
returns `None` for an unpriced model (e.g. `FakeProvider`'s default
`"fake-model"`) rather than raising or guessing.

`CostTracker` accumulates spend across calls under a `threading.Lock`:

```python
class CostTracker:
    def record(self, model: str, usage: Usage) -> float | None: ...
    @property
    def total_usd(self) -> float: ...
    @property
    def request_count(self) -> int: ...
    def by_model(self) -> dict[str, float]: ...   # snapshot, keyed by model
    def reset(self) -> None: ...
```

You generally don't call this directly: `Engine` owns one `CostTracker`
instance and calls `record()` after every completion, then stamps the
result back onto the response —

```python
# src/aiforge/core/engine.py
def _track_cost(self, response: ChatResponse) -> ChatResponse:
    cost = self.cost_tracker.record(response.model, response.usage)
    if cost is None:
        return response
    return dataclasses.replace(response, cost_usd=cost)
```

— which is exactly why `ChatResponse.cost_usd` is documented as populated
centrally rather than by the provider. Read accumulated totals off the
engine at any time: `forge.engine.cost_tracker.total_usd`,
`forge.engine.cost_tracker.by_model()`.

## 5. Multi-provider routing

`ProviderRouter` (`src/aiforge/providers/router.py`) picks a provider for a
request and calls it, applying routing rules, retry, and fallback.

```python
@dataclass(frozen=True, slots=True)
class RoutingRule:
    match: str              # substring, matched case-insensitively against a hint
    provider: str           # registry alias
    model: str | None = None
```

### Selection

`select(*, provider=None, model=None, hint="")` — an explicit `provider`
argument always wins outright. Otherwise each `RoutingRule` is checked in
order; the first whose `match.lower()` is a substring of `hint.lower()`
wins (`hint` is typically the prompt). If nothing matches, `default_provider`
is used. An explicit `model` argument always overrides whatever the rule
would have picked.

### Fallback and retry

`call(build_request, *, provider=None, model=None, hint="")` builds a
candidate chain — the selected provider first, then every entry in
`fallback_order` that isn't already the selected provider — and tries each
in turn:

```python
_TRANSIENT_ERRORS = (ProviderRateLimitError, ProviderTimeoutError)
```

For each candidate, the request is retried against **that same provider**
up to `max_attempts` times (exponential backoff + jitter, via
`retry_with_backoff`) but only for the two transient error types above. Any
`ProviderError` — whether it's a non-transient error like
`ProviderAuthError`/`ProviderResponseError` (raised immediately, no retry)
or a transient error that exhausted its retries — causes the router to move
on to the **next** candidate in the chain. The first candidate that returns
successfully wins; if every candidate in the chain fails, the last error
encountered is re-raised.

`build_request` is called once per candidate with that candidate's
effective model, so each fallback provider gets a request built against its
own appropriate default model when the caller didn't pin one explicitly.

### Config-driven routing

`RoutingConfig` (`src/aiforge/config/schema.py`) is the TOML-shaped version
of the same policy:

```python
@dataclass(frozen=True, slots=True)
class RoutingRuleConfig:
    match: str
    provider: str
    model: str | None = None

@dataclass(frozen=True, slots=True)
class RoutingConfig:
    rules: tuple[RoutingRuleConfig, ...] = ()
    fallback_order: tuple[str, ...] = ()
    max_attempts: int = 2
```

```toml
[routing]
rules = [
  { match = "architecture", provider = "smart" },
]
fallback_order = ["fast", "smart"]
max_attempts = 2
```

`Engine.from_config` converts each `RoutingRuleConfig` into a `RoutingRule`
and passes `fallback_order`/`max_attempts` straight through when building
the `ProviderRouter`. The `provider` strings in `rules`/`fallback_order` are
registry aliases — they must already be registered (via entry points or
`register_factory`, see §6) by the time the router is built; `[routing]`
only expresses *policy*, it doesn't register new provider aliases itself.

### Two aliases, one implementation

Because routing rules and `fallback_order` refer to providers by their
**registry alias** rather than by class, you can register the same
provider class twice under different names with different bound models —
e.g. a cheap/fast tier and an expensive/careful tier that are both
`AnthropicProvider`:

```python
from aiforge.providers.anthropic_provider import AnthropicProvider
from aiforge.providers.registry import ProviderRegistry
from aiforge.providers.router import ProviderRouter, RoutingRule

registry = ProviderRegistry()
registry.register_factory("fast", lambda: AnthropicProvider(model="claude-haiku-4-5"))
registry.register_factory("smart", lambda: AnthropicProvider(model="claude-opus-4-8"))

router = ProviderRouter(
    registry,
    default_provider="fast",
    rules=(RoutingRule(match="architecture", provider="smart"),),
    fallback_order=("fast", "smart"),
)
```

Both aliases wrap `AnthropicProvider`, whose `name` class attribute is
always the fixed string `"anthropic"` — so `response.provider` is
`"anthropic"` no matter which alias served the call. What tells you *which
configured route* actually handled a request is the registry alias, not
that fixed identity string:

- `RoutedResponse.provider_name` — the alias from the fallback chain that
  succeeded, returned by `ProviderRouter.call()`.
- `TaskContext.provider_name` (`src/aiforge/core/context.py`) — the same
  value, threaded through by `Engine.run()` (`context =
  TaskContext(..., provider_name=routed.provider_name, ...)`).

The test suite exercises this exact distinction
(`tests/unit/test_core_engine.py::test_run_context_provider_name_is_registry_alias_not_self_reported_name`,
using two `FakeProvider` aliases): a `"flaky"` alias configured to fail and
a `"healthy"` fallback alias both self-report `provider="fake"` on the
response, but `context.provider_name` correctly reports `"healthy"` — the
alias that actually served the request.

## 6. Adding a new provider

Implement `BaseProvider` (or satisfy the `Provider` protocol directly if you
don't want the `acomplete` thread-offload default):

```python
# my_package/providers.py
from collections.abc import AsyncIterator, Iterator

from aiforge.providers.base import BaseProvider
from aiforge.providers.types import ChatRequest, ChatResponse, StreamChunk, Usage


class OpenAIProvider(BaseProvider):
    name = "openai"

    def __init__(self, *, model: str = "gpt-5", api_key: str | None = None) -> None:
        self.model = model
        # lazily import your SDK here, same pattern as AnthropicProvider,
        # so importing this module doesn't require the SDK to be installed
        ...

    def complete(self, request: ChatRequest) -> ChatResponse:
        ...

    def stream(self, request: ChatRequest) -> Iterator[StreamChunk]:
        ...

    async def astream(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        ...

    def count_tokens(self, request: ChatRequest) -> int:
        ...
```

No AIForge core file needs to change. Register it either way:

**Manually**, for scripts, tests, or dynamic setups:

```python
from aiforge.providers.registry import ProviderRegistry

registry = ProviderRegistry()
registry.register_factory("openai", OpenAIProvider)
# or a lambda/closure if you need to bind config: lambda: OpenAIProvider(model="gpt-5")
```

`register_factory` takes a keyword-args-only factory — a class whose
`__init__` takes only keyword arguments (like `OpenAIProvider` above, or
`AnthropicProvider`/`FakeProvider`) works directly, since
`ProviderRegistry.get_or_create(name, **kwargs)` calls it as
`factory(**kwargs)`.

**Via entry points**, for installable packages — declare the group
`aiforge.providers` in your package's `pyproject.toml`, matching how this
repo registers its own built-in providers:

```toml
# this repo's own pyproject.toml
[project.entry-points."aiforge.providers"]
anthropic = "aiforge.providers.anthropic_provider:AnthropicProvider"
fake = "aiforge.providers.fake:FakeProvider"
```

```toml
# a third-party package's pyproject.toml
[project.entry-points."aiforge.providers"]
openai = "my_package.providers:OpenAIProvider"
```

Once that package is installed, `ProviderRegistry.discover_entry_points()`
(called automatically by `Engine.from_config`) picks it up — safe to call
more than once, and an already-registered name is left alone unless you
call `register_factory(..., replace=True)` explicitly. Either registration
path — manual or entry point — requires editing exactly one new file
(`providers/*.py` or your package's own module); nothing in `src/aiforge`
changes.

## 7. `FakeProvider`

`src/aiforge/providers/fake.py` is a fully in-memory `Provider`
implementation: zero network calls, zero cost, deterministic output. It's
registered under the `fake` entry point like any other provider, and is
what the test suite, `examples/quickstart.py`, and `examples/streaming.py`
all run against by default.

```python
class FakeProvider(BaseProvider):
    name = "fake"

    def __init__(self, *, model: str = "fake-model",
                 respond_fn: Callable[[ChatRequest], str] | None = None,
                 stream_chunk_size: int = 12,
                 fail_times: int = 0,
                 fail_error: Exception | None = None) -> None: ...
```

- `respond_fn` overrides the default response builder, which echoes back
  the last non-empty message, truncated to 200 characters, wrapped in
  `"This is a response from the fake provider for: {prompt}"`.
- `stream_chunk_size` controls how many characters `stream()`/`astream()`
  yield per `StreamChunk`.
- `fail_times`/`fail_error` make the first *N* calls raise (default:
  `ProviderRateLimitError("fake provider simulated rate limit",
  retry_after=0.0)`) — this is how the router's retry/fallback behavior
  (§5) is exercised in tests without touching the network.
- `count_tokens()` (and internal usage accounting) uses a deterministic
  ~4-characters-per-token approximation — good enough to exercise
  cost-tracking and usage-reporting code paths without a real tokenizer.
  Since `"fake-model"` isn't in `PRICING` (§4), `cost_usd` stays `None`
  unless you construct it with a priced model name, e.g.
  `FakeProvider(model="claude-haiku-4-5")`.

To run without an API key at all, point `default_provider` at `"fake"`:

```toml
[engine]
default_provider = "fake"
```

```python
from aiforge import AIForge
from aiforge.config.schema import AIForgeConfig, EngineConfig

forge = AIForge(config=AIForgeConfig(engine=EngineConfig(default_provider="fake")))
response = forge.run("Write a Python function that reverses a linked list.")
```

Swapping `default_provider` back to `"anthropic"` (with `ANTHROPIC_API_KEY`
set) runs the identical code path against real Claude — nothing else in the
call site changes, which is the point of the `Provider` abstraction.

## See also

- [../README.md](../README.md) — project overview and quickstart
- [architecture.md](architecture.md) — layering, dependency injection, extensibility contracts
- [api.md](api.md) — `AIForge` facade, CLI, HTTP server
- [plugin-development.md](plugin-development.md) — adding a provider without touching core
- [skill-creation.md](skill-creation.md) — the `skill.toml` schema and authoring workflow
- [performance.md](performance.md) — benchmark methodology and measured results
- [repo-optimization.md](repo-optimization.md) — why the repo stays small
