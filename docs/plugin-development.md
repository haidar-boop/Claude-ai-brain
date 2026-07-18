# Plugin Development Guide

This guide covers shipping a new AI **provider** as an installable AIForge plugin: the contract
you implement, the two ways to register it, a minimal worked example package, how to test it, and
how to translate your backend's exceptions so `ProviderRouter` retry/fallback works correctly.

This document is about *providers* — the thing that talks to an LLM API. AIForge's other plugin
mechanism, the **skill system** (teaching the framework a new programming language or coding
convention via a `skill.toml` manifest), is a separate extension point with its own entry-point
group and schema; see [`skill-creation.md`](skill-creation.md) instead. Nothing below applies to
skills, and nothing in `skill-creation.md` applies to providers.

## 1. The contract

A provider either subclasses `aiforge.providers.base.BaseProvider` or simply satisfies
`aiforge.providers.base.Provider` structurally — it's a `@runtime_checkable typing.Protocol`, so
`isinstance(x, Provider)` holds for any object with the right shape, whether or not it inherits
from anything:

```python
# src/aiforge/providers/base.py
@runtime_checkable
class Provider(Protocol):
    """The contract every AI provider implementation must satisfy."""

    name: str
    model: str

    def complete(self, request: ChatRequest) -> ChatResponse:
        """Run a single, non-streaming completion."""
        ...

    def stream(self, request: ChatRequest) -> Iterator[StreamChunk]:
        """Run a streaming completion, yielding incremental chunks."""
        ...

    async def acomplete(self, request: ChatRequest) -> ChatResponse:
        """Async completion."""
        ...

    def astream(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        """Run an async streaming completion, yielding incremental chunks."""
        ...

    def count_tokens(self, request: ChatRequest) -> int:
        """Return the provider's own token count for *request* (input side)."""
        ...
```

In practice, subclass `BaseProvider`, the ABC both built-in providers (`AnthropicProvider`,
`FakeProvider`) use:

```python
# src/aiforge/providers/base.py
class BaseProvider(ABC):
    name: str
    model: str

    @abstractmethod
    def complete(self, request: ChatRequest) -> ChatResponse:
        """Run a single, non-streaming completion."""

    @abstractmethod
    def stream(self, request: ChatRequest) -> Iterator[StreamChunk]:
        """Run a streaming completion, yielding incremental chunks."""

    async def acomplete(self, request: ChatRequest) -> ChatResponse:
        """Async completion. Default: offload the sync :meth:`complete` to a thread."""
        return await asyncio.to_thread(self.complete, request)

    @abstractmethod
    def astream(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        """Run an async streaming completion, yielding incremental chunks."""

    @abstractmethod
    def count_tokens(self, request: ChatRequest) -> int:
        """Return the provider's own token count for *request* (input side)."""
```

Four methods are abstract — you must implement `complete`, `stream`, `astream`, and `count_tokens`
directly. `acomplete` is the one exception: it has a concrete default that offloads your
synchronous `complete()` to a thread via `asyncio.to_thread`. Only override it if your backend has
a genuinely native async client, the way `AnthropicProvider` and `FakeProvider` both do. There is
no safe generic way to turn a synchronous streaming *generator* into a real async one (it either
blocks the event loop or needs a thread+queue bridge with its own cancellation edge cases), which
is why `astream` has no default and every provider implements it directly.

`name` and `model` are plain attributes, not methods:

- `name` is a fixed class attribute identifying the *implementation* — set once, e.g.
  `FakeProvider.name = "fake"`, `AnthropicProvider.name = "anthropic"`.
- `model` is an instance attribute: the provider's default model, set in `__init__` and
  overridable per-request. Every built-in provider resolves the effective model as
  `request.model or self.model` when it builds the backend call — follow the same convention.

The request/response types your methods trade in (`ChatRequest`, `ChatResponse`, `Message`,
`Role`, `StreamChunk`, `Usage`) live in `src/aiforge/providers/types.py` and are documented in full
in [`providers.md`](providers.md). One contract worth calling out here because it's easy to get
wrong: a stream is zero or more `StreamChunk(text=..., is_final=False)` chunks followed by
*exactly one* trailing `StreamChunk(text="", is_final=True, usage=...)` — both `stream()` and
`astream()` must emit that trailing chunk, even for an empty response.

### Reference implementation: `FakeProvider`

`src/aiforge/providers/fake.py` (about 100 lines) is a complete, real, tested `Provider`
implementation with zero external dependencies — the fastest way to see the whole contract
satisfied at once. Its constructor is a useful shape to copy:

```python
class FakeProvider(BaseProvider):
    name = "fake"

    def __init__(
        self,
        *,
        model: str = "fake-model",
        respond_fn: Callable[[ChatRequest], str] | None = None,
        stream_chunk_size: int = 12,
        fail_times: int = 0,
        fail_error: Exception | None = None,
    ) -> None: ...
```

`respond_fn` lets a caller override how it builds response text; `fail_times`/`fail_error` make
the first *N* calls raise (a `ProviderRateLimitError` by default) — that's the hook the test suite
uses to exercise `ProviderRouter`'s retry/fallback behavior without touching a network. Read the
full file directly, and its test file, `tests/unit/test_providers_fake.py` (§4 below explains how
to use both as a template).

## 2. Registering a provider

Registration is handled by `ProviderRegistry` (`src/aiforge/providers/registry.py`), a
lazily-instantiating registry of provider *factories*, not instances:

```python
class ProviderRegistry:
    def register_factory(
        self, name: str, factory: Callable[..., Provider], *, replace: bool = False
    ) -> None: ...
    def discover_entry_points(self) -> None: ...
    def get_or_create(self, name: str, **kwargs: object) -> Provider: ...
    def require(self, name: str) -> Provider: ...
    def names(self) -> list[str]: ...
```

There are two ways to get a provider into it. Neither requires editing any file under
`src/aiforge`.

### Manual: `register_factory`

For programmatic/in-process setups — tests, scripts, or anywhere you're building the engine
yourself:

```python
from aiforge.providers.registry import ProviderRegistry

registry = ProviderRegistry()
registry.register_factory("myprovider", lambda: MyProvider())
```

`register_factory` takes a **keyword-args-only factory**: `ProviderRegistry.require(name)` and the
plain `get_or_create(name)` (no kwargs) — which is what `ProviderRouter` and `Engine` always
call internally — invoke your factory with *zero* arguments. A bare class works directly only if
every constructor parameter is optional (like `FakeProvider` or `AnthropicProvider`); if your
provider needs a required argument bound at registration time (an API key, a base URL, a pinned
model), close over it with a lambda, exactly like this repo's own example does when registering two
differently-configured instances of the same class:

```python
# examples/multi_provider_routing.py
registry.register_factory("general", lambda: FakeProvider(model="general-model"))
registry.register_factory("systems", lambda: FakeProvider(model="systems-model"))
```

Pass `replace=True` to overwrite an existing registration (this also evicts any cached instance);
without it, registering a name twice raises `ValueError`. Calling `get_or_create(name, **kwargs)`
*with* kwargs always builds a fresh, uncached instance — the instance cache only applies to the
zero-argument path that `require()` uses.

### Entry point: an installable package

For a provider you want to `pip install` into any AIForge project with zero code changes at the
call site, declare the `aiforge.providers` entry-point group in your package's `pyproject.toml`.
This is exactly how this repo registers its own built-in providers:

```toml
# this repo's own pyproject.toml
[project.entry-points."aiforge.providers"]
anthropic = "aiforge.providers.anthropic_provider:AnthropicProvider"
fake = "aiforge.providers.fake:FakeProvider"
```

A third-party package does the same thing, pointing at its own module:

```toml
# your package's pyproject.toml
[project.entry-points."aiforge.providers"]
myprovider = "my_package:MyProvider"
```

Once that package is installed (`pip install`, or `pip install -e .` for local development),
`ProviderRegistry.discover_entry_points()` picks it up:

```python
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

You never have to call this yourself in normal use: `Engine.from_config()` — which both
`aiforge.api.client.AIForge` and the `aiforge` CLI build on — calls it automatically on every
construction:

```python
# src/aiforge/core/engine.py
provider_registry = ProviderRegistry()
provider_registry.discover_entry_points()
```

So the entire integration surface for an out-of-tree provider package is: write the class, add the
three-line entry-point table above, `pip install` it. Nothing in `src/aiforge` changes, and nothing
at the call site changes either — point `[engine] default_provider` (or a `[routing]` rule) at your
provider's registered name and it's live. `aiforge providers list` (which itself just builds a
fresh `ProviderRegistry` and calls `discover_entry_points()`) is the fastest way to confirm a
newly installed package was picked up.

## 3. Worked example: a minimal provider plugin package

`examples/custom_skill/` in this repo is the skill-side version of this pattern — an installable
package that adds an "elixir" skill via the `aiforge.skills` entry-point group with no changes to
`src/aiforge`. Below is the provider-side equivalent: a complete, copyable `aiforge-provider-echo`
package that echoes the last user message back verbatim.

```
aiforge-provider-echo/
├── pyproject.toml
└── src/
    └── aiforge_provider_echo/
        └── __init__.py
```

`pyproject.toml`:

```toml
[build-system]
requires = ["hatchling>=1.25"]
build-backend = "hatchling.build"

[project]
name = "aiforge-provider-echo"
version = "0.1.0"
description = "Example out-of-tree AIForge provider: echoes the prompt back."
requires-python = ">=3.11"
dependencies = ["aiforge"]

[project.entry-points."aiforge.providers"]
echo = "aiforge_provider_echo:EchoProvider"

[tool.hatch.build.targets.wheel]
packages = ["src/aiforge_provider_echo"]

[tool.hatch.build]
include = ["src/aiforge_provider_echo/**/*.py"]
```

`src/aiforge_provider_echo/__init__.py`:

```python
"""EchoProvider: echoes the last user message back verbatim.

Demonstrates the plugin contract for shipping a provider as an installable
package rather than adding it to AIForge's own src/aiforge/providers/
directory. Register the class under the ``aiforge.providers`` entry-point
group in pyproject.toml; AIForge discovers it automatically once this
package is installed -- no AIForge core file changes.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

from aiforge.providers.base import BaseProvider
from aiforge.providers.types import ChatRequest, ChatResponse, StreamChunk, Usage

__all__ = ["EchoProvider"]


class EchoProvider(BaseProvider):
    """Returns the last user message verbatim. No network calls, no dependencies."""

    name = "echo"

    def __init__(self, *, model: str = "echo-model") -> None:
        self.model = model

    def complete(self, request: ChatRequest) -> ChatResponse:
        text = _last_user_message(request)
        usage = Usage(
            input_tokens=self.count_tokens(request),
            output_tokens=max(1, len(text) // 4),
        )
        return ChatResponse(
            text=text,
            model=request.model or self.model,
            provider=self.name,
            usage=usage,
            stop_reason="end_turn",
        )

    def stream(self, request: ChatRequest) -> Iterator[StreamChunk]:
        response = self.complete(request)
        if response.text:
            yield StreamChunk(text=response.text)
        yield StreamChunk(text="", is_final=True, usage=response.usage)

    async def astream(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        for chunk in self.stream(request):
            yield chunk

    def count_tokens(self, request: ChatRequest) -> int:
        text = " ".join(m.content for m in request.messages)
        return max(1, len(text) // 4)


def _last_user_message(request: ChatRequest) -> str:
    return next((m.content for m in reversed(request.messages) if m.content), "")
```

Note there's no `acomplete` — `BaseProvider`'s thread-offload default handles it, which is the
whole point of only four methods being abstract.

Try it:

```bash
pip install -e ./aiforge-provider-echo
aiforge providers list          # prints: anthropic, echo, fake
aiforge run "hello there" --provider echo
```

```python
from aiforge import AIForge
from aiforge.config.schema import AIForgeConfig, EngineConfig

forge = AIForge(config=AIForgeConfig(engine=EngineConfig(default_provider="echo")))
assert forge.run("hello there").text == "hello there"
```

A real backend provider (OpenAI, Gemini, a local model server, an internal gateway) follows the
same package shape — only `complete`/`stream`/`astream`/`count_tokens` get more interesting, per
§5 below. For a full narrated example of a production-shaped `complete`/`stream`/`astream`
implementation (lazy SDK import, request building, response parsing), read
[`providers.md`](providers.md), which walks `AnthropicProvider` end to end.

## 4. Testing your provider

Test against the same protocol contract this repo tests its own providers against, not against
your backend's SDK mocked out ad hoc. Two files are the models to follow:

- `tests/unit/test_providers_base.py` — a minimal `_MinimalProvider(BaseProvider)` that implements
  only the four abstract methods, used to verify `isinstance(provider, Provider)` holds and that
  the inherited `acomplete` thread-offload default actually matches synchronous `complete()`.
- `tests/unit/test_providers_fake.py` — the fuller contract suite: response shape, streaming
  reassembly, sync/async agreement, token counting, and simulated-failure behavior.

Adapted for a provider of your own, the same tests look like:

```python
from aiforge.providers.base import Provider
from aiforge.providers.types import ChatRequest, Message, Role

from aiforge_provider_echo import EchoProvider


def _request(prompt: str = "hello") -> ChatRequest:
    return ChatRequest(messages=(Message(role=Role.USER, content=prompt),), model="echo-model")


def test_conforms_to_provider_protocol() -> None:
    assert isinstance(EchoProvider(), Provider)


def test_stream_reassembles_to_same_text_as_complete() -> None:
    provider = EchoProvider()
    complete_text = provider.complete(_request("hi there")).text
    stream_text = "".join(c.text for c in provider.stream(_request("hi there")))
    assert stream_text == complete_text


def test_stream_last_chunk_is_final_with_usage() -> None:
    chunks = list(EchoProvider().stream(_request()))
    assert chunks[-1].is_final is True
    assert chunks[-1].usage is not None


async def test_astream_matches_sync_stream() -> None:
    provider = EchoProvider()
    sync_chunks = [c.text for c in provider.stream(_request())]
    async_chunks = [c.text async for c in provider.astream(_request())]
    assert sync_chunks == async_chunks


async def test_acomplete_matches_sync_complete() -> None:
    provider = EchoProvider()
    assert (await provider.acomplete(_request())).text == provider.complete(_request()).text


def test_count_tokens_is_positive_for_nonempty_prompt() -> None:
    assert EchoProvider().count_tokens(_request("some text")) > 0
```

If your provider talks to a real backend, also add `FakeProvider`-style `fail_times`/`fail_error`
(or equivalent) hooks and tests mirroring `test_fail_times_raises_then_recovers` /
`test_custom_fail_error_is_raised_verbatim` — that's how you prove your error translation (§5)
raises the right AIForge exception type under simulated failure, without needing the real backend
to actually be down. You do **not** need to re-test `ProviderRouter`'s retry/fallback *logic*
itself — `tests/unit/test_providers_router.py`
(`test_call_falls_back_when_primary_provider_rate_limited`,
`test_call_retries_transient_error_before_succeeding`) already covers that against `FakeProvider`
stand-ins, and the router's behavior is provider-agnostic. Your responsibility is narrower and
more important: prove that your `complete`/`stream`/`astream` actually raise `ProviderRateLimitError`
or `ProviderTimeoutError` (not your backend SDK's native exception types) when the backend fails —
get that right and the already-tested router logic handles the rest correctly for free.

### Integration-style tests without hitting a real API

Two ways to exercise the full pipeline (config → skill resolution → provider call → cost
tracking) against your provider without touching the network, matching how this repo's own
examples do it:

**Your package is installed** (e.g. `pip install -e .` in CI) — let entry-point discovery find it,
the same way `examples/quickstart.py` swaps in `FakeProvider`:

```python
from aiforge import AIForge
from aiforge.config.schema import AIForgeConfig, EngineConfig

forge = AIForge(config=AIForgeConfig(engine=EngineConfig(default_provider="echo")))
response = forge.run("Write a Python function that reverses a linked list.")
```

**Pure in-process, nothing installed** — wire a `ProviderRegistry` and `Engine` directly, the same
way `examples/multi_provider_routing.py` does:

```python
from aiforge.core.context import TaskRequest
from aiforge.core.engine import Engine
from aiforge.providers.registry import ProviderRegistry
from aiforge.providers.router import ProviderRouter
from aiforge.skills.registry import SkillRegistry
from aiforge.skills.resolver import SkillResolver

registry = ProviderRegistry()
registry.register_factory("echo", EchoProvider)
router = ProviderRouter(registry, default_provider="echo")
engine = Engine(router=router, skill_resolver=SkillResolver(SkillRegistry()))

result = engine.run(TaskRequest(prompt="hello there"))
assert result.response.text == "hello there"
```

`FakeProvider` itself remains the right default choice for testing *your own application code*
that merely depends on *some* provider — reach for your own provider in tests only when the thing
under test is the provider itself, or your app's behavior genuinely depends on that provider's
specific output shape.

## 5. Error translation

Your provider's `complete`/`stream`/`astream` should never let a backend SDK's native exception
type escape untranslated. Translate it to AIForge's provider error hierarchy
(`src/aiforge/core/errors.py`) before re-raising:

```python
class ProviderError(AIForgeError):
    """Base class for AI-provider related errors."""

class ProviderAuthError(ProviderError):
    """Raised when a provider rejects credentials (missing or invalid key)."""

class ProviderRateLimitError(ProviderError):
    """Raised when a provider's rate limit is exceeded."""
    def __init__(self, message: str, *, retry_after: float | None = None) -> None: ...

class ProviderTimeoutError(ProviderError):
    """Raised when a provider request exceeds its configured timeout."""

class ProviderResponseError(ProviderError):
    """Raised when a provider returns an unexpected or invalid response."""
```

(`ProviderNotFoundError` also lives in this module, but it's raised by `ProviderRegistry` itself
on a missing name — not something your provider's request-handling code constructs.)

The general shape: catch broadly around the backend call, translate, chain the original as the
cause so it's never lost from a traceback:

```python
def complete(self, request: ChatRequest) -> ChatResponse:
    try:
        raw = self._client.some_call(**self._build_params(request))
    except Exception as exc:
        raise self._translate_error(exc) from exc
    return self._to_chat_response(raw)
```

`AnthropicProvider._translate_error` is the real, in-repo version of this pattern — a good
template for the exception types a typical HTTP-based LLM SDK raises:

```python
# src/aiforge/providers/anthropic_provider.py
def _translate_error(self, exc: Exception) -> Exception:
    anthropic = self._anthropic
    if isinstance(exc, anthropic.AuthenticationError):
        return ProviderAuthError(str(exc))
    if isinstance(exc, anthropic.RateLimitError):
        return ProviderRateLimitError(str(exc), retry_after=_parse_retry_after(exc))
    if isinstance(exc, anthropic.APITimeoutError):
        return ProviderTimeoutError(str(exc))
    if isinstance(exc, anthropic.APIStatusError):
        return ProviderResponseError(str(exc))
    return exc
```

`AnthropicProvider` also logs the request/outcome around this via
`aiforge.providers.logging.log_request_start` / `log_response` / `log_request_error` — debug-level
only, secrets redacted. Reuse those same three functions if you want your provider's logs to look
like the rest of AIForge's; it's optional, not part of the `Provider` contract.

### Why the mapping matters: this is what `ProviderRouter` reads

`ProviderRouter.call()` only knows how to react correctly to *AIForge's* exception types — not your
backend's (routing and fallback selection themselves are covered in full in
[`providers.md`](providers.md) §5). It declares exactly two exception types as transient:

```python
# src/aiforge/providers/router.py
_TRANSIENT_ERRORS: tuple[type[BaseException], ...] = (
    ProviderRateLimitError,
    ProviderTimeoutError,
)
```

What actually happens on failure depends on which of three buckets your raised exception falls
into:

| What your provider raises | Router behavior |
| --- | --- |
| `ProviderRateLimitError` / `ProviderTimeoutError` | retried against the *same* candidate up to `max_attempts` times (exponential backoff + jitter via `retry_with_backoff`); falls back to the next candidate only if retries are exhausted |
| any other `ProviderError` (`ProviderAuthError`, `ProviderResponseError`, ...) | not retried — the router moves immediately to the next candidate in `fallback_order` |
| anything that is **not** a `ProviderError` (an untranslated SDK exception, a bare `ValueError`, ...) | not caught by the router at all — propagates straight out of `ProviderRouter.call()`, aborting the whole request with no retry and no fallback to any remaining candidate |

That third row is the one that bites silently: `retry_with_backoff`'s `except tuple(retry_on):`
only matches the transient pair, and `router.call()`'s own `except ProviderError` only matches
`ProviderError` subclasses — so an exception that is neither simply skips both catch clauses and
exits the whole call chain immediately. A provider that forgets to translate, say, a raw
connection-reset error means one flaky network blip takes down a request that a correctly
configured `fallback_order` should have quietly recovered from. Only `ProviderRateLimitError` and
`ProviderTimeoutError` get retried before falling back — everything else you translate still
participates in fallback, just without wasted retries against a candidate that's never going to
succeed on retry (wrong credentials, malformed response).

If your backend's own SDK doesn't already retry transient failures internally (the `anthropic`
package does, via its client's own `max_retries`/`timeout`), you can reuse AIForge's backoff
helper inside your provider for that inner layer:

```python
# src/aiforge/providers/retry.py
def retry_with_backoff(
    func: Callable[[], T],
    *,
    retry_on: Sequence[type[BaseException]] = (Exception,),
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    jitter: float = 0.25,
    sleep: Callable[[float], None] = time.sleep,
) -> T: ...
```

This is a separate, provider-internal concern from `ProviderRouter`'s cross-provider
retry-then-fallback — the two compose: your provider retries its own transient hiccups internally,
and if it still gives up, raises a translated `ProviderRateLimitError`/`ProviderTimeoutError` so
the router's cross-provider fallback remains the outer safety net.

## Checklist

- `name` (class attribute) and `model` (instance attribute) set; `complete`, `stream`, `astream`,
  `count_tokens` implemented; `acomplete` only if you have a real async client to call natively.
- Optional backend SDK imported lazily, inside `__init__` — not at module level — so merely
  importing your module (e.g. while `aiforge providers list` enumerates registrations) never
  requires the SDK to be installed. See `AnthropicProvider.__init__`.
- Every backend exception you can reasonably anticipate is translated to `ProviderAuthError` /
  `ProviderRateLimitError` / `ProviderTimeoutError` / `ProviderResponseError` via
  `raise translated from exc`.
- Registered via `register_factory` (in-process) or
  `[project.entry-points."aiforge.providers"]` (installable package) — pick one per use case, both
  work simultaneously across a codebase.
- Tests mirror `tests/unit/test_providers_fake.py` / `test_providers_base.py`: protocol
  conformance, `complete`/`stream`/`astream`/`acomplete` agreement, positive `count_tokens`, and
  simulated-failure tests proving your translation raises the right AIForge exception type.
- `aiforge providers list` (after installing) shows your provider's registered name.

## See also

- [../README.md](../README.md) — project overview and quickstart
- [architecture.md](architecture.md) — layering, dependency injection, extensibility contracts
- [providers.md](providers.md) — Claude setup, the `Provider` protocol, cost tracking, routing
- [api.md](api.md) — `AIForge` facade, CLI, HTTP server
- [skill-creation.md](skill-creation.md) — the `skill.toml` schema and authoring workflow
- [performance.md](performance.md) — benchmark methodology and measured results
- [repo-optimization.md](repo-optimization.md) — why the repo stays small
