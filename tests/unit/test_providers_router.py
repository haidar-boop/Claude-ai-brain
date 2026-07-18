"""Tests for aiforge.providers.router."""

from __future__ import annotations

import pytest

from aiforge.core.errors import ProviderNotFoundError
from aiforge.providers.fake import FakeProvider
from aiforge.providers.registry import ProviderRegistry
from aiforge.providers.router import ProviderRouter, RoutingRule
from aiforge.providers.types import ChatRequest, Message, Role


def _build_request(model: str) -> ChatRequest:
    return ChatRequest(messages=(Message(role=Role.USER, content="hi"),), model=model)


def test_select_explicit_provider_wins() -> None:
    router = ProviderRouter(ProviderRegistry(), default_provider="default")
    provider, model = router.select(provider="explicit", model="m")
    assert provider == "explicit"
    assert model == "m"


def test_select_matches_rule_by_hint() -> None:
    rules = (RoutingRule(match="rust", provider="rust-provider", model="rust-model"),)
    router = ProviderRouter(ProviderRegistry(), default_provider="default", rules=rules)
    provider, model = router.select(hint="please write some Rust code")
    assert provider == "rust-provider"
    assert model == "rust-model"


def test_select_falls_back_to_default_when_no_rule_matches() -> None:
    router = ProviderRouter(ProviderRegistry(), default_provider="default")
    provider, model = router.select(hint="anything")
    assert provider == "default"
    assert model is None


def test_select_explicit_model_overrides_rule_model() -> None:
    rules = (RoutingRule(match="rust", provider="rust-provider", model="rust-default"),)
    router = ProviderRouter(ProviderRegistry(), default_provider="default", rules=rules)
    _, model = router.select(model="pinned-model", hint="rust")
    assert model == "pinned-model"


def test_call_succeeds_on_first_matching_provider() -> None:
    registry = ProviderRegistry()
    registry.register_factory("fake", lambda: FakeProvider(model="fake-model"))
    router = ProviderRouter(registry, default_provider="fake")
    routed = router.call(_build_request, hint="hello")
    assert routed.provider_name == "fake"
    assert routed.response.provider == "fake"


def test_call_uses_providers_own_default_model_when_unpinned() -> None:
    registry = ProviderRegistry()
    registry.register_factory("fake", lambda: FakeProvider(model="provider-default"))
    router = ProviderRouter(registry, default_provider="fake")
    routed = router.call(_build_request, hint="hello")
    assert routed.response.model == "provider-default"


def test_call_falls_back_when_primary_provider_rate_limited() -> None:
    registry = ProviderRegistry()
    registry.register_factory("flaky", lambda: FakeProvider(model="flaky-model", fail_times=99))
    registry.register_factory("healthy", lambda: FakeProvider(model="healthy-model"))
    router = ProviderRouter(
        registry, default_provider="flaky", fallback_order=("flaky", "healthy"), max_attempts=1
    )
    routed = router.call(_build_request, hint="hello")
    # The registry alias that actually served the request is "healthy", the
    # fallback -- distinct from the initially-selected "flaky" alias, and
    # distinct from the provider implementation's own self-reported name
    # ("fake" for both, since they're both FakeProvider instances).
    assert routed.provider_name == "healthy"
    assert routed.response.provider == "fake"
    assert routed.response.model == "healthy-model"


def test_call_raises_last_error_when_all_providers_exhausted() -> None:
    registry = ProviderRegistry()
    registry.register_factory("flaky", lambda: FakeProvider(fail_times=99))
    router = ProviderRouter(registry, default_provider="flaky", max_attempts=1)
    with pytest.raises(Exception, match="rate limit"):
        router.call(_build_request, hint="hello")


def test_call_raises_provider_not_found_when_default_is_unregistered() -> None:
    router = ProviderRouter(ProviderRegistry(), default_provider="missing")
    with pytest.raises(ProviderNotFoundError):
        router.call(_build_request, hint="hello")


def test_call_retries_transient_error_before_succeeding() -> None:
    registry = ProviderRegistry()
    registry.register_factory("fake", lambda: FakeProvider(model="m", fail_times=1))
    router = ProviderRouter(
        registry,
        default_provider="fake",
        max_attempts=2,
        retry_base_delay=0.001,
        retry_sleep=lambda _: None,
    )
    routed = router.call(_build_request, hint="hello")
    assert routed.response.text
