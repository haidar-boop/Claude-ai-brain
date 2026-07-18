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

[Unreleased]: https://github.com/haidar-boop/claude-ai-brain/commits/claude/ai-coding-framework-design-eq7nrm
