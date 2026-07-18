# Changelog

All notable changes to this project are documented in this file. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Initial release of AIForge: modular AI coding framework.
- Provider abstraction layer (`aiforge.providers`) with `Provider` protocol, request/response/usage
  neutral types, cost tracking, rule-based routing, and entry-point-based provider discovery.
- `AnthropicProvider` — official `anthropic` SDK integration (lazy import, streaming, retry via
  SDK, `ANTHROPIC_API_KEY` from environment only).
- `FakeProvider` — deterministic, zero-cost provider for tests, examples, and local development.
- Plugin skill system (`aiforge.skills`) — TOML manifests, directory + entry-point discovery,
  compatibility validation, conflict resolution, task-based scoring and composition.
- Ten built-in skills: Python, JavaScript, TypeScript, Rust, Go, C++, Java, SQL, HTML/CSS, Bash.
- Core engine (`aiforge.core`) with dependency injection container, generic registry, event bus,
  and a typed exception hierarchy.
- Layered configuration (`aiforge.config`): defaults → `aiforge.toml` → environment variables.
- `AIForge` Python facade, `aiforge` CLI, and an optional stdlib-only HTTP JSON server.
- Performance utilities: LRU+TTL cache, inverted index, async bounded-concurrency helper,
  PEP 562 lazy-import machinery, optional `orjson` acceleration.
- Benchmarks (startup, cache, serialization, skill loading) and a repository size report script.
- Full documentation set, GitHub Actions CI (tests, lint, benchmarks, CodeQL).

### Fixed (pre-release review findings)

- `AnthropicProvider` now translates `anthropic.APIConnectionError` to a new
  `ProviderConnectionError` (transient: retried and eligible for fallback), with an `APIError`
  catch-all so no SDK exception ever escapes the `AIForgeError` hierarchy untranslated.
- `ProviderRegistry` and `Container` singleton caches are now lock-guarded — concurrent first-use
  callers share one instance instead of each constructing their own.
- `SkillResolver` scores a prompt token matching a skill's own name (+3) and deduplicates repeated
  explicit skill names.
- `SkillManifest` strictly validates `priority` (integer) and `enabled` (boolean) instead of
  silently coercing strings (`bool("false")` is `True`).
- Config loader rejects a bare string where an array is required
  (`fallback_order = "anthropic"` no longer silently becomes a tuple of characters).
- `Engine` honors an explicit `max_tokens=0` instead of replacing it with the default.
- HTTP server: per-connection socket timeout (30s) against stalled clients; `"skills": null`
  now behaves like an omitted field instead of returning a confusing 400.
- `aiforge.utils.serialization` stdlib fallback serializes `datetime`/`date`/`time` like the
  orjson path (TOML configs can contain real date objects).
- `aiforge.utils.logging.configure()` is thread-safe (no duplicate handlers on concurrent first
  use).
- Singleton locks (`ProviderRegistry`, `Container`) are reentrant (`RLock`), so a factory that
  composes other registrations on the same thread cannot deadlock.
- Cost estimation clamps negative wire-supplied token counts to zero and returns `None` on float
  overflow instead of letting `OverflowError` escape post-response accounting.
- `AnthropicProvider.count_tokens` no longer forwards `temperature` (not accepted by
  `messages.count_tokens`); `retry_after` parsing rejects negative/non-finite header values.
- One broken third-party entry point (provider or skill) is logged and skipped instead of
  aborting discovery and taking the built-ins down with it.
- `AIFORGE_LOG_LEVEL` is normalized and validated (lowercase works; garbage falls back to
  WARNING with a warning instead of making the library unimportable); `redact()` masks compound
  secret keys (`anthropic_api_key`, `client_secret`, `auth_token`) while leaving token-count
  fields alone.
- Env overrides are type-checked against the schema (`AIFORGE__...=4k` into an int field, or an
  over-deep key path replacing a scalar with a dict, now raise `ConfigError`); pathologically
  nested TOML raises `ConfigError`/`SkillValidationError` instead of a bare `RecursionError`.
- Skill manifest list fields must contain only strings (mixed TOML arrays are rejected at load
  time instead of crashing later in indexing/scoring).
- The stdlib JSON fallback sets `allow_nan=False` (never emits spec-invalid `NaN`/`Infinity`
  tokens) and its date/datetime handling is now exercised by tests even when orjson is installed.

[Unreleased]: https://github.com/haidar-boop/claude-ai-brain/commits/claude/ai-coding-framework-design-eq7nrm
