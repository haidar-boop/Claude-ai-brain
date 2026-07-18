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

[Unreleased]: https://github.com/haidar-boop/claude-ai-brain/commits/claude/ai-coding-framework-design-eq7nrm
