# API Reference

AIForge exposes one underlying `Engine` (`aiforge.core.engine.Engine`) through three surfaces: a
Python facade (`aiforge.api.client.AIForge`), a command-line tool (`aiforge`, console-script entry
point `aiforge.api.cli:main`), and an optional local HTTP JSON API (`aiforge serve`,
`aiforge.server.app`). The CLI and HTTP server are thin wrappers around the same `AIForge` facade
documented in §1 — neither does anything you can't do directly in Python. See
[`architecture.md`](architecture.md) for how `Engine` resolves skills and routes to a provider
internally; this document is the call-signature-level reference for all three surfaces.

## 1. Python facade — `aiforge.api.client.AIForge`

### Constructing an `AIForge`

```python
class AIForge:
    def __init__(
        self, config: AIForgeConfig | None = None, *, config_path: Path | str | None = None
    ) -> None: ...
```

`__init__` does exactly two things: resolve a config, then build an engine from it.

```python
self.config = config if config is not None else load_config(project_path=config_path)
self.engine = Engine.from_config(self.config)
```

- Pass nothing to let `load_config()` resolve the usual layered path: shipped
  `src/aiforge/config/defaults.toml`, then `$AIFORGE_CONFIG` or `./aiforge.toml` if present, then
  environment variables (see [`../README.md`](../README.md#configuration)).
- Pass `config_path` to point `load_config()` at a specific project TOML file instead of
  `./aiforge.toml`.
- Pass a fully-built `config` to skip file/env resolution entirely — `config_path` is ignored
  whenever `config` is not `None`.

Both `forge.config` (the resolved `AIForgeConfig`) and `forge.engine` (the `Engine`) are plain
public attributes, e.g. `forge.engine.cost_tracker.total_usd` reads accumulated spend.

```python
from aiforge import AIForge

forge = AIForge()  # aiforge.toml in cwd (or $AIFORGE_CONFIG), else shipped defaults
```

```python
from aiforge import AIForge

forge = AIForge(config_path="configs/staging.toml")
```

```python
from aiforge import AIForge
from aiforge.config.schema import AIForgeConfig, EngineConfig

# Zero-cost, zero-network: route everything to the built-in FakeProvider.
forge = AIForge(config=AIForgeConfig(engine=EngineConfig(default_provider="fake")))
```

### `run()`

```python
def run(
    self,
    prompt: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    skills: Sequence[str] = (),
    system: str | None = None,
    max_tokens: int | None = None,
    file_hints: Sequence[str] = (),
) -> ChatResponse: ...
```

Runs `prompt` through the engine and returns just the provider's response — literally
`self.run_detailed(...).response` underneath (§`run_detailed` below covers the discarded
resolution detail).

- `provider` — registry alias to use (`"anthropic"`, `"fake"`, or a custom alias registered via
  `ProviderRegistry.register_factory`). `None` lets `ProviderRouter` pick via routing rules, then
  `default_provider`.
- `model` — overrides the model string sent in the request; wins over any routing-rule model and
  the provider's own default.
- `skills` — explicit skill names. Non-empty means "use exactly these" (each name is looked up
  with `SkillRegistry.require()`, raising `SkillNotFoundError` if unknown); empty (the default)
  auto-resolves skills from `prompt` and `file_hints` instead.
- `system` — extra system-prompt text, composed alongside skill guidance into the final system
  prompt (see `composed_system` under `run_detailed` below).
- `max_tokens` — caps output tokens; `None` falls back to `Engine.default_max_tokens` (`4096`
  unless overridden, via `Engine.from_config`, by `[providers.<default provider>].max_tokens` — see
  [`providers.md`](providers.md) §1).
- `file_hints` — file paths or glob patterns used only for skill auto-detection (e.g. a `*.py`
  hint nudges the resolver toward the `python` skill); never sent to the provider itself.

```python
from aiforge import AIForge

forge = AIForge()
response = forge.run(
    "Write a Python function that reverses a linked list.",
    provider="fake",
    skills=["python"],
)
print(response.text)
print(response.provider, response.model, response.usage.total_tokens)
```

### `run_detailed()`

```python
def run_detailed(
    self,
    prompt: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    skills: Sequence[str] = (),
    system: str | None = None,
    max_tokens: int | None = None,
    file_hints: Sequence[str] = (),
) -> EngineResult: ...
```

Identical keyword arguments to `run()`, but returns the full `EngineResult`
(`aiforge.core.engine.EngineResult`) instead of just the response:

```python
@dataclass(frozen=True, slots=True)
class EngineResult:
    response: ChatResponse
    context: TaskContext
```

`context` is a `TaskContext` (`aiforge.core.context.TaskContext`):

```python
@dataclass(slots=True)
class TaskContext:
    request: TaskRequest
    provider_name: str
    model: str
    resolved_skills: tuple[str, ...]
    composed_system: str | None
```

- `context.provider_name` — the **registry alias** that actually served the request (e.g.
  `"fake"`), not necessarily equal to `response.provider` (the provider implementation's own fixed
  identity string). Two aliases can wrap the same provider class under different names — see
  [`providers.md`](providers.md) §5 "Two aliases, one implementation".
- `context.model` — the resolved model actually used; same value as `response.model`.
- `context.resolved_skills` — names of the skills the resolver selected, whether passed explicitly
  via `skills=` or auto-resolved from the prompt/`file_hints`.
- `context.composed_system` — the final system prompt sent to the provider (engine `base_system` +
  the `system` kwarg + each selected skill's `SkillManifest.prompt_guidance()`, joined with blank
  lines), or `None` if nothing contributed one.

Neither `EngineResult` nor `TaskContext` is part of the lazy top-level `aiforge` API (see the
return-types table at the end of this section) — import them directly if you need the types for
annotations.

```python
from aiforge import AIForge

forge = AIForge()
result = forge.run_detailed("How do I structure a Flask app?", skills=["python"])

print(result.context.provider_name, result.context.model)
print(result.context.resolved_skills)        # ('python',)
print(result.context.composed_system[:40])   # '## python skill\nPython language, ecosy...'
print(result.response.text)
```

### `stream()`

```python
def stream(
    self,
    prompt: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    skills: Sequence[str] = (),
    system: str | None = None,
    max_tokens: int | None = None,
    file_hints: Sequence[str] = (),
) -> Iterator[StreamChunk]: ...
```

Same keyword arguments as `run()`. Builds a `TaskRequest(..., stream=True)` and yields from
`Engine.stream()`. Streaming **never retries or falls back across providers** — once a chunk has
reached the caller, silently restarting on a different provider would corrupt or duplicate the
stream (see [`architecture.md`](architecture.md) "Streaming bypasses router retry/fallback").

`StreamChunk` (`aiforge.providers.types.StreamChunk`):

```python
@dataclass(frozen=True, slots=True)
class StreamChunk:
    text: str
    is_final: bool = False
    usage: Usage | None = None
```

A stream is zero or more chunks with `is_final=False` (incremental text, `usage=None`), followed by
exactly one trailing chunk with `is_final=True` carrying `text=""` and the completed `Usage`.
Consumers that only want the assembled text can ignore `is_final`/`usage` and just concatenate
`.text`.

```python
from aiforge import AIForge

forge = AIForge()
for chunk in forge.stream("Explain what a linked list is, in three sentences.", provider="fake"):
    print(chunk.text, end="", flush=True)
    if chunk.is_final and chunk.usage is not None:
        print(f"\n\n[{chunk.usage.total_tokens} tokens]")
```

### `astream()`

```python
async def astream(
    self,
    prompt: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    skills: Sequence[str] = (),
    system: str | None = None,
    max_tokens: int | None = None,
    file_hints: Sequence[str] = (),
) -> AsyncIterator[StreamChunk]: ...
```

Async twin of `stream()` — same keyword arguments, same chunk contract, backed by `Engine.astream()`
(which awaits `provider.astream()` directly rather than threading a sync generator through a
thread).

```python
import asyncio
from aiforge import AIForge

async def main() -> None:
    forge = AIForge()
    async for chunk in forge.astream("hello", provider="fake"):
        print(chunk.text, end="")

asyncio.run(main())
```

### `run_many()`

```python
def run_many(self, prompts: Sequence[str], *, concurrency: int = 4) -> list[ChatResponse]: ...
```

Runs each of `prompts` independently through `Engine.arun()`, bounded to at most `concurrency`
requests in flight at once via `aiforge.utils.async_utils.bounded_gather` (a semaphore-guarded
`asyncio.gather`), and returns responses **in the same order as `prompts`**, regardless of which
finishes first.

Two behaviors are easy to assume incorrectly from the name, so they're worth stating exactly as
implemented:

- **No per-prompt overrides.** Each prompt runs as a bare `TaskRequest(prompt=prompt)` —
  `run_many` does not accept `provider`, `model`, `skills`, `system`, `max_tokens`, or
  `file_hints`. Every prompt runs against the engine's default provider/model and auto-resolved
  skills. For per-prompt overrides, fan out `run()` or `run_detailed()` calls yourself (e.g. across
  a `ThreadPoolExecutor`, or your own `asyncio.gather` over coroutines that call `engine.arun`
  directly).
- **Owns its own event loop.** `run_many` calls `asyncio.run(...)` internally, so it's a
  synchronous method meant to be called from sync code. Calling it from inside a running event loop
  raises `RuntimeError: asyncio.run() cannot be called from a running event loop` — use `astream`
  or `await self.engine.arun(...)` directly in that context instead.

```python
from aiforge import AIForge

forge = AIForge()
responses = forge.run_many(
    [
        "Summarize the CAP theorem in one sentence.",
        "Summarize the actor model in one sentence.",
        "Summarize CRDTs in one sentence.",
    ],
    concurrency=2,
)
for r in responses:
    print(r.text)
```

### Return types at a glance

| Type | Defined in | `from aiforge import ...`? |
| --- | --- | --- |
| `ChatResponse` | `aiforge.providers.types` | Yes |
| `Usage` | `aiforge.providers.types` | Yes |
| `StreamChunk` | `aiforge.providers.types` | No — `from aiforge.providers.types import StreamChunk` |
| `EngineResult` | `aiforge.core.engine` | No — `from aiforge.core.engine import EngineResult` |
| `TaskContext` | `aiforge.core.context` | No — `from aiforge.core.context import TaskContext` |

`aiforge/__init__.py` exposes a deliberately narrow set of names lazily via PEP 562 (`AIForge`,
`AIForgeConfig`, `ChatRequest`, `ChatResponse`, `Engine`, `Message`, `Role`, `SkillManifest`,
`Usage`, `__version__`); anything else — including `StreamChunk`, `EngineResult`, and
`TaskContext` — is imported from its defining module directly. `ChatResponse` itself
(`aiforge.providers.types.ChatResponse`) carries `text`, `model`, `provider`, `usage: Usage`,
`stop_reason: str | None`, `cost_usd: float | None` (populated centrally by `CostTracker`, `None`
means unpriced rather than free — see [`providers.md`](providers.md) §4), and `raw: Any` (the
provider SDK's raw response object).

## 2. CLI — `aiforge`

The `aiforge` console script (`aiforge.api.cli:main`, registered under `[project.scripts]` in
`pyproject.toml`) is an `argparse` program built by `_build_parser()`. Every subcommand handler
imports its own dependencies lazily inside the handler function, so a lightweight invocation like
`aiforge --version` never imports the engine, any provider SDK, or the skill system.

Global flags, valid before the subcommand name:

| Flag | Effect |
| --- | --- |
| `--version` | Print `aiforge <version>` and exit immediately (`argparse` `action="version"`, raises `SystemExit(0)`). |
| `--config PATH` | Path to `aiforge.toml` (default: `./aiforge.toml` or `$AIFORGE_CONFIG`), forwarded by `run`, `skills list`/`show`, and `config show`/`path`. **Not** forwarded by `serve` (see the note under `aiforge serve` below); unused by `providers list` and `version`, which don't load config at all. |

Running `aiforge` with no subcommand, or a subcommand group with no sub-subcommand (`aiforge`,
`aiforge skills`, `aiforge providers`, `aiforge config`), prints the top-level help and returns
exit code `1`. Any exception raised by a handler is caught by `main()`, printed as `error: <exc>`
to stderr, and turned into exit code `1` — nothing ever reaches an unhandled traceback:

```
$ aiforge run hi --provider does-not-exist
error: no provider registered as 'does-not-exist' (available: anthropic, fake)
```

The examples below use `--provider fake` so they run with no API key and no network access, exactly
like `examples/quickstart.py`. Swap in `--provider anthropic` (or drop `--provider` if
`aiforge.toml` already defaults to `anthropic`) once `ANTHROPIC_API_KEY` is set in the environment
— see [`providers.md`](providers.md) §1.

### `aiforge run PROMPT`

```
aiforge run PROMPT [--provider PROVIDER] [--model MODEL] [--skill NAME ...]
                    [--system TEXT] [--max-tokens N] [--stream]
```

| Flag | Notes |
| --- | --- |
| `prompt` (positional) | The prompt to send. |
| `--provider` | Override the provider to use. |
| `--model` | Override the model to use. |
| `--skill` | Explicit skill name; **repeatable** (`--skill python --skill sql`), collected into a list via `action="append"`. |
| `--system` | Additional system prompt text. |
| `--max-tokens` | Max output tokens (`int`). |
| `--stream` | Stream the response incrementally instead of printing it all at once. |

There is no `--file-hint` flag — `file_hints` is reachable only through the Python facade.

Non-streaming success prints the response text to stdout, then — **only if `response.cost_usd` is
not `None`** — a cost line to stderr in the exact form built in `_cmd_run`:

```python
print(response.text)
if response.cost_usd is not None:
    print(
        f"\n[{result.context.provider_name}/{response.model}] "
        f"cost: ${response.cost_usd:.4f}  tokens: {response.usage.total_tokens}",
        file=sys.stderr,
    )
```

`FakeProvider`'s default model (`"fake-model"`) has no entry in the pricing table, so `cost_usd`
stays `None` and plain `--provider fake` runs print no cost line at all:

```
$ aiforge run "Write a Python function that reverses a linked list." --provider fake
This is a response from the fake provider for: Write a Python function that reverses a linked list.
```

Pinning a *priced* model name with `--model` (still served by the zero-cost `FakeProvider` — this
is not a real Claude call) demonstrates the cost line deterministically, at zero cost and with no
API key, because `FakeProvider`'s token counting is a fixed ~4-chars/token estimate:

```
$ aiforge run "Write a Python function that reverses a linked list." --provider fake --model claude-haiku-4-5
This is a response from the fake provider for: Write a Python function that reverses a linked list.

[fake/claude-haiku-4-5] cost: $0.0020  tokens: 1918
```

(stdout carries the response text; the `[provider/model] cost: ... tokens: ...` line is on stderr,
so it won't pollute `aiforge run ... > out.txt` redirection.) Against real Claude
(`--provider anthropic`), the same cost line appears because `claude-opus-4-8` (the default model)
is priced in `PRICING` — see [`providers.md`](providers.md) §4.

`--skill` is repeatable and combines with the prompt normally:

```
$ aiforge run "Show me a SQL query joining two tables" --provider fake --skill python --skill sql
This is a response from the fake provider for: Show me a SQL query joining two tables
```

An unknown `--skill` name fails the same way an unknown skill fails everywhere else in the
framework (`SkillRegistry.require()` raising `SkillNotFoundError`):

```
$ aiforge run hi --provider fake --skill nonexistent
error: no skill registered as 'nonexistent' (available: bash, cpp, go, htmlcss, java, javascript, python, rust, sql, typescript)
```

`--stream` prints chunks as they arrive with no separating whitespace, then a trailing newline —
and **never** prints a cost line, streaming or not (only the non-streaming branch computes and
prints one):

```
$ aiforge run "streaming demo" --provider fake --stream
This is a response from the fake provider for: streaming demo
```

### `aiforge skills list [--all]`

Prints one line per skill: `<name>[ (disabled)]: <description>`. Without `--all`, only enabled
skills are listed (`SkillRegistry.names(enabled_only=True)`); with `--all`, disabled skills are
included too, each suffixed ` (disabled)`. All ten shipped skills are enabled out of the box, so
the two forms currently produce identical output unless you've disabled some via
`[skills] disabled = [...]` in `aiforge.toml`.

```
$ aiforge skills list
bash: POSIX-conscious Bash scripting for reliable automation and CLI tooling.
cpp: Modern C++ (C++17/20) memory safety, RAII, and performance-critical systems programming.
go: Go concurrency model, error handling idiom, and standard-library-first design.
htmlcss: Semantic HTML5, modern CSS layout, accessibility, and responsive design.
java: Modern Java (17+) idioms, the Spring ecosystem, and JVM performance considerations.
javascript: Modern JavaScript (ES2022+) for browser and Node.js applications.
python: Python language, ecosystem, and idiomatic patterns for scripting, web backends, and data work.
rust: Rust ownership model, safety guarantees, and idiomatic systems programming.
sql: SQL query design, indexing strategy, and safe parameterized data access across PostgreSQL/MySQL.
typescript: TypeScript type system and patterns for safer, more maintainable JavaScript.
```

### `aiforge skills show NAME`

Prints the skill's full `SkillManifest.prompt_guidance()` text — the same Markdown-ish guidance
block the engine composes into the system prompt when that skill is selected:

```
$ aiforge skills show python
## python skill
Python language, ecosystem, and idiomatic patterns for scripting, web backends, and data work.

### Languages
- python

### Frameworks
- Django
- FastAPI
- Flask
- pytest
- SQLAlchemy
- Celery
...
```

(truncated here — the real output continues through Libraries, Coding patterns, Best practices,
Debugging strategies, Optimization strategies, Testing approach, Code review rules, and
Documentation style.) An unknown name raises `SkillNotFoundError`, reported the same way as the
`--skill nonexistent` example above.

### `aiforge providers list`

Prints every provider name `ProviderRegistry.discover_entry_points()` finds via the
`aiforge.providers` entry-point group, sorted:

```
$ aiforge providers list
anthropic
fake
```

### `aiforge config show`

Prints the fully merged `AIForgeConfig` (defaults → `aiforge.toml` → environment) as compact,
key-sorted JSON — `dumps(dataclasses.asdict(config), sort_keys=True)`:

```
$ aiforge config show
{"engine":{"default_provider":"anthropic"},"providers":{"anthropic":{"extra":{},"max_retries":2,"max_tokens":4096,"model":"claude-opus-4-8","timeout":600.0}},"routing":{"fallback_order":[],"max_attempts":2,"rules":[]},"skills":{"disabled":[],"enabled":null,"extra_dirs":[]}}
```

### `aiforge config path`

Prints which path `load_config()` would read as the project file — `args.config or
os.environ.get("AIFORGE_CONFIG") or str(DEFAULT_CONFIG_PATH)`, where `DEFAULT_CONFIG_PATH =
Path("aiforge.toml")`. This is pure string resolution; it doesn't check whether the file exists.

```
$ aiforge config path
aiforge.toml

$ aiforge --config /tmp/custom.toml config path
/tmp/custom.toml
```

### `aiforge serve [--host HOST] [--port PORT]`

Starts the HTTP JSON API — see §3 for the endpoints themselves.

| Flag | Default |
| --- | --- |
| `--host` | `127.0.0.1` |
| `--port` | `8420` |

```
$ aiforge serve --host 127.0.0.1 --port 8420
AIForge server listening on http://127.0.0.1:8420  (POST /run, GET /health)
```

> **Note:** the global `--config PATH` flag is parsed but **not** threaded through to `serve`
> (`_cmd_serve` calls `serve(host=args.host, port=args.port)`, ignoring `args.config`). The server
> always builds a fresh default `AIForge()`, which resolves config the normal way from the
> *server process's* working directory (`$AIFORGE_CONFIG` env var, or `./aiforge.toml`). To pin the
> server to a specific config file, set `AIFORGE_CONFIG` in the environment before running
> `aiforge serve` rather than relying on `--config`.

### `aiforge version`

Prints the bare version string (`aiforge.__about__.__version__`) and returns normally — distinct
from the global `--version` flag, which prints `aiforge <version>` and exits via `SystemExit`
before any subcommand logic runs:

```
$ aiforge version
0.1.0

$ aiforge --version
aiforge 0.1.0
```

## 3. HTTP server — `aiforge serve` / `aiforge.server.app`

`aiforge.server.app` is a **minimal, dependency-free** JSON API over the engine: one
`http.server.ThreadingHTTPServer`, stdlib only. It has **no authentication, no TLS, and no rate
limiting** — this is explicitly a local-development convenience, not something to expose beyond
`127.0.0.1` or a trusted network. The module docstring states this plainly:

> Deliberately small: one POST endpoint that runs a prompt through the engine and returns the
> response as JSON, plus a health check. No authentication, no TLS, no rate limiting -- this
> exists so `aiforge serve` works out of the box with zero extra dependencies for local
> development. Front it with a real ASGI/WSGI server and framework for anything beyond that.

### Starting it

```python
def serve(*, host: str = "127.0.0.1", port: int = 8420, forge: AIForge | None = None) -> None: ...
```

Blocks (`server.serve_forever()`) until interrupted with Ctrl+C, at which point it calls
`server.server_close()` and returns. `forge` defaults to a plain `AIForge()` when omitted — pass
your own pre-configured instance (e.g. one built with `AIForge(config=...)`) to embed the server in
a larger program:

```python
from aiforge import AIForge
from aiforge.config.schema import AIForgeConfig, EngineConfig
from aiforge.server.app import serve

forge = AIForge(config=AIForgeConfig(engine=EngineConfig(default_provider="fake")))
serve(host="0.0.0.0", port=8420, forge=forge)
```

### `GET /health`

```
$ curl -s http://127.0.0.1:8420/health
{"status": "ok"}
```

Any other `GET` path returns `404 {"error": "not found"}`.

### `POST /run`

Request body — JSON object, `prompt` required, everything else optional and passed straight
through to `forge.run_detailed(...)`:

```json
{
  "prompt": "Write a haiku about databases.",
  "provider": "fake",
  "model": null,
  "skills": ["sql"],
  "system": null,
  "max_tokens": null
}
```

There is no `file_hints` field — the HTTP API surfaces the same six fields `_cmd_run` does, minus
`--stream` (streaming isn't exposed over HTTP at all, only `POST /run`'s single-shot response).

Response body — built field-by-field in `do_POST`, in this exact shape and key order:

```json
{
  "text": "...",
  "provider": "fake",
  "model": "fake-model",
  "stop_reason": "end_turn",
  "cost_usd": null,
  "usage": {
    "input_tokens": 2265,
    "output_tokens": 19,
    "total_tokens": 2284
  }
}
```

`"provider"` here is `result.context.provider_name` (the registry alias that served the request),
not `response.provider` — the same distinction documented for `run_detailed()` in §1.

### curl walkthrough

Against a server started with `default_provider="fake"` (zero cost, zero network, zero API key —
identical setup to the CLI examples in §2):

```bash
$ curl -s -X POST http://127.0.0.1:8420/run \
    -H 'Content-Type: application/json' \
    -d '{"prompt": "Write a haiku about databases.", "provider": "fake", "skills": ["sql"]}'
{"text": "This is a response from the fake provider for: Write a haiku about databases.", "provider": "fake", "model": "fake-model", "stop_reason": "end_turn", "cost_usd": null, "usage": {"input_tokens": 2265, "output_tokens": 19, "total_tokens": 2284}}
```

### Errors: 400 vs 502

`do_POST` splits failures by exception type, exactly:

```python
try:
    payload = self._read_json_body()
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt:
        raise ValueError("'prompt' must be a non-empty string")
    result = forge.run_detailed(...)
except (KeyError, ValueError, TypeError) as exc:
    self._json_response(400, {"error": str(exc)})
    return
except Exception as exc:
    self._json_response(502, {"error": str(exc)})
    return
```

- **`400`** — bad input: a missing/empty `prompt`, a malformed JSON body (`json.loads` raising
  `json.JSONDecodeError`, a `ValueError` subclass), a JSON body that isn't an object, or an empty
  request body.
- **`502`** — anything else, in practice provider-side failures (`ProviderNotFoundError`,
  `ProviderAuthError`, `ProviderRateLimitError`, ...) that reach `do_POST` after exhausting the
  engine's own retry/fallback chain (see [`architecture.md`](architecture.md) "Request flow"). None
  of AIForge's own exception types subclass `KeyError`/`ValueError`/`TypeError`, so any
  `AIForgeError` always lands in the `502` branch.

```bash
$ curl -s -w '\n%{http_code}\n' -X POST http://127.0.0.1:8420/run -d '{}'
{"error": "'prompt' must be a non-empty string"}
400

$ curl -s -w '\n%{http_code}\n' -X POST http://127.0.0.1:8420/run -d '{not valid json'
{"error": "Expecting property name enclosed in double quotes: line 1 column 2 (char 1)"}
400

$ curl -s -w '\n%{http_code}\n' -X POST http://127.0.0.1:8420/run \
    -d '{"prompt": "hi", "provider": "does-not-exist"}'
{"error": "no provider registered as 'does-not-exist' (available: anthropic, fake)"}
502
```

### Request body size cap

`_read_json_body` rejects request bodies over `_MAX_BODY_BYTES = 10 * 1024 * 1024` (10 MB) — read
from `Content-Length`, checked *before* the body is read off the socket:

```python
length = int(self.headers.get("Content-Length", 0))
if length <= 0:
    raise ValueError("empty request body")
if length > _MAX_BODY_BYTES:
    raise ValueError("request body too large")
```

Both conditions are `ValueError`, so both surface as `400`, not `502`.

## See also

- [../README.md](../README.md) — project overview and quickstart
- [architecture.md](architecture.md) — layering, dependency injection, extensibility contracts
- [providers.md](providers.md) — Claude setup, adding a new provider, routing
- [plugin-development.md](plugin-development.md) — adding a provider without touching core
- [skill-creation.md](skill-creation.md) — the `skill.toml` schema and authoring workflow
- [performance.md](performance.md) — benchmark methodology and measured results
- [repo-optimization.md](repo-optimization.md) — why the repo stays small
