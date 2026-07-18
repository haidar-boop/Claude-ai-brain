"""Tests for aiforge.core.engine."""

from __future__ import annotations

from aiforge.config.schema import (
    AIForgeConfig,
    EngineConfig,
    ProviderConfig,
    RoutingConfig,
    RoutingRuleConfig,
)
from aiforge.core.context import TaskRequest
from aiforge.core.engine import Engine
from aiforge.providers.fake import FakeProvider
from aiforge.providers.registry import ProviderRegistry
from aiforge.providers.router import ProviderRouter
from aiforge.skills.manifest import SkillManifest
from aiforge.skills.registry import SkillRegistry
from aiforge.skills.resolver import SkillResolver


def _build_engine(*, python_skill: bool = False) -> Engine:
    registry = ProviderRegistry()
    registry.register_factory("fake", lambda: FakeProvider(model="fake-model"))
    router = ProviderRouter(registry, default_provider="fake", max_attempts=1)
    skill_registry = SkillRegistry()
    if python_skill:
        skill_registry.register(
            SkillManifest(
                name="python",
                description="Python skill",
                languages=("python",),
                best_practices=("follow PEP 8",),
            )
        )
    return Engine(router=router, skill_resolver=SkillResolver(skill_registry))


def test_run_returns_response_and_context() -> None:
    engine = _build_engine()
    result = engine.run(TaskRequest(prompt="hello"))
    assert result.response.provider == "fake"
    assert result.context.provider_name == "fake"
    assert result.context.model == "fake-model"


def test_run_context_provider_name_is_registry_alias_not_self_reported_name() -> None:
    # Two distinct registry aliases wrapping the *same* provider implementation
    # (both FakeProvider, which always self-reports provider="fake"). The
    # fallback alias that actually serves the request ("healthy") must be
    # reflected in context.provider_name, not the provider's own fixed name.
    registry = ProviderRegistry()
    registry.register_factory("flaky", lambda: FakeProvider(model="flaky-model", fail_times=99))
    registry.register_factory("healthy", lambda: FakeProvider(model="healthy-model"))
    router = ProviderRouter(
        registry, default_provider="flaky", fallback_order=("flaky", "healthy"), max_attempts=1
    )
    engine = Engine(router=router, skill_resolver=SkillResolver(SkillRegistry()))
    result = engine.run(TaskRequest(prompt="hello"))
    assert result.context.provider_name == "healthy"
    assert result.response.provider == "fake"


def test_run_cost_usd_none_for_unpriced_fake_model() -> None:
    engine = _build_engine()
    result = engine.run(TaskRequest(prompt="hello"))
    assert result.response.cost_usd is None  # "fake-model" has no pricing table entry


def test_run_composes_skill_guidance_into_system_prompt() -> None:
    engine = _build_engine(python_skill=True)
    result = engine.run(TaskRequest(prompt="write a python function"))
    assert "python" in result.context.resolved_skills
    assert result.context.composed_system is not None
    assert "PEP 8" in result.context.composed_system


def test_run_explicit_skill_selection() -> None:
    engine = _build_engine(python_skill=True)
    result = engine.run(TaskRequest(prompt="anything", skills=("python",)))
    assert result.context.resolved_skills == ("python",)


def test_run_base_system_is_prepended() -> None:
    registry = ProviderRegistry()
    registry.register_factory("fake", lambda: FakeProvider(model="fake-model"))
    router = ProviderRouter(registry, default_provider="fake")
    engine = Engine(
        router=router,
        skill_resolver=SkillResolver(SkillRegistry()),
        base_system="You are AIForge.",
    )
    result = engine.run(TaskRequest(prompt="hi"))
    assert result.context.composed_system == "You are AIForge."


def test_run_request_system_is_included() -> None:
    engine = _build_engine()
    result = engine.run(TaskRequest(prompt="hi", system="Be terse."))
    assert result.context.composed_system == "Be terse."


def test_run_emits_lifecycle_events() -> None:
    engine = _build_engine()
    seen: list[str] = []
    engine.events.subscribe("engine.request_started", lambda e: seen.append(e.name))
    engine.events.subscribe("engine.request_completed", lambda e: seen.append(e.name))
    engine.run(TaskRequest(prompt="hi"))
    assert seen == ["engine.request_started", "engine.request_completed"]


async def test_arun_matches_run() -> None:
    engine = _build_engine()
    sync_result = engine.run(TaskRequest(prompt="hi"))
    async_result = await engine.arun(TaskRequest(prompt="hi"))
    assert sync_result.response.text == async_result.response.text


def test_stream_yields_chunks_that_assemble_to_expected_text() -> None:
    engine = _build_engine()
    chunks = list(engine.stream(TaskRequest(prompt="hello streaming world")))
    assert chunks[-1].is_final is True
    assembled = "".join(c.text for c in chunks)
    assert "hello streaming world" in assembled


def test_stream_tracks_cost_for_priced_model() -> None:
    registry = ProviderRegistry()
    registry.register_factory("fake", lambda: FakeProvider(model="claude-haiku-4-5"))
    router = ProviderRouter(registry, default_provider="fake")
    engine = Engine(router=router, skill_resolver=SkillResolver(SkillRegistry()))
    list(engine.stream(TaskRequest(prompt="hello")))
    assert engine.cost_tracker.total_usd > 0


async def test_astream_yields_chunks() -> None:
    engine = _build_engine()
    chunks = [c async for c in engine.astream(TaskRequest(prompt="hello"))]
    assert chunks[-1].is_final is True


def test_run_tracks_cost_for_priced_model() -> None:
    registry = ProviderRegistry()
    registry.register_factory("fake", lambda: FakeProvider(model="claude-opus-4-8"))
    router = ProviderRouter(registry, default_provider="fake")
    engine = Engine(router=router, skill_resolver=SkillResolver(SkillRegistry()))
    result = engine.run(TaskRequest(prompt="hello"))
    assert result.response.cost_usd is not None
    assert result.response.cost_usd > 0
    assert engine.cost_tracker.total_usd == result.response.cost_usd


def test_from_config_builds_working_engine() -> None:
    config = AIForgeConfig(engine=EngineConfig(default_provider="fake"))
    engine = Engine.from_config(config)
    result = engine.run(TaskRequest(prompt="hello"))
    assert result.response.provider == "fake"


def test_from_config_wires_routing_rules() -> None:
    config = AIForgeConfig(
        engine=EngineConfig(default_provider="fake"),
        routing=RoutingConfig(
            rules=(RoutingRuleConfig(match="rust", provider="fake", model="rust-model"),)
        ),
    )
    engine = Engine.from_config(config)
    provider, model = engine.router.select(hint="write some rust")
    assert provider == "fake"
    assert model == "rust-model"


def test_from_config_wires_provider_config_model_into_construction() -> None:
    # [providers.fake].model must reach the actual FakeProvider instance,
    # not just sit unused in AIForgeConfig -- this is what _configure_providers
    # (via ProviderRegistry.configure) exists to guarantee.
    config = AIForgeConfig(
        engine=EngineConfig(default_provider="fake"),
        providers={"fake": ProviderConfig(model="configured-model")},
    )
    engine = Engine.from_config(config)
    result = engine.run(TaskRequest(prompt="hello"))
    assert result.response.model == "configured-model"


def test_from_config_default_max_tokens_from_provider_config() -> None:
    config = AIForgeConfig(
        engine=EngineConfig(default_provider="fake"),
        providers={"fake": ProviderConfig(model="fake-model", max_tokens=8192)},
    )
    engine = Engine.from_config(config)
    assert engine.default_max_tokens == 8192
    # End-to-end: an unset TaskRequest.max_tokens should reach the provider
    # as 8192, not the hardcoded 4096 fallback.
    engine.router.registry.configure(
        "fake", model="fake-model", respond_fn=lambda request: str(request.max_tokens)
    )
    result = engine.run(TaskRequest(prompt="hello"))
    assert result.response.text == "8192"


def test_run_explicit_max_tokens_zero_is_not_replaced_by_default() -> None:
    # Regression: `request.max_tokens or default` treated an explicit 0 as
    # unset. 0 must reach the provider so the backend rejects it loudly.
    registry = ProviderRegistry()
    registry.register_factory(
        "probe", lambda: FakeProvider(model="m", respond_fn=lambda req: str(req.max_tokens))
    )
    router = ProviderRouter(registry, default_provider="probe")
    engine = Engine(router=router, skill_resolver=SkillResolver(SkillRegistry()))
    assert engine.run(TaskRequest(prompt="x", max_tokens=0)).response.text == "0"
    assert engine.run(TaskRequest(prompt="x", max_tokens=None)).response.text == "4096"
    assert engine.run(TaskRequest(prompt="x", max_tokens=1)).response.text == "1"


def test_from_config_ignores_provider_config_for_unregistered_provider_name() -> None:
    # Config referencing a provider that isn't installed/registered must not
    # raise -- there's simply nothing to configure.
    config = AIForgeConfig(
        engine=EngineConfig(default_provider="fake"),
        providers={"not-installed": ProviderConfig(model="whatever")},
    )
    engine = Engine.from_config(config)
    result = engine.run(TaskRequest(prompt="hello"))
    assert result.response.provider == "fake"
