"""Rule-based provider selection and fallback routing.

Lets multiple providers coexist: pick a provider (and model) per request
based on simple substring-match rules against a hint (typically the prompt
or composed system text), with an ordered fallback chain and
transient-error retry, so one overloaded or rate-limited provider doesn't
take the whole system down when another provider is registered.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from aiforge.core.errors import (
    ProviderConnectionError,
    ProviderError,
    ProviderNotFoundError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)
from aiforge.providers.base import Provider
from aiforge.providers.registry import ProviderRegistry
from aiforge.providers.retry import retry_with_backoff
from aiforge.providers.types import ChatRequest, ChatResponse

__all__ = ["ProviderRouter", "RoutedResponse", "RoutingRule"]

_TRANSIENT_ERRORS: tuple[type[BaseException], ...] = (
    ProviderConnectionError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)


@dataclass(frozen=True, slots=True)
class RoutingRule:
    """Route requests whose *hint* text contains *match* (case-insensitive)."""

    match: str
    provider: str
    model: str | None = None


@dataclass(frozen=True, slots=True)
class RoutedResponse:
    """The result of :meth:`ProviderRouter.call`: a response plus which registry
    alias actually served it.

    *provider_name* is the registry alias from the fallback chain that
    succeeded -- not necessarily the one initially selected, and not
    necessarily equal to ``response.provider`` (the provider implementation's
    own fixed identity, e.g. ``"anthropic"``). Two aliases can wrap the same
    implementation (two ``AnthropicProvider`` instances configured with
    different models under names like ``"fast"``/``"smart"``), so callers
    that need to know *which configured route* handled a request must use
    this field, not ``response.provider``.
    """

    response: ChatResponse
    provider_name: str


class ProviderRouter:
    """Selects a provider for a request and calls it, applying rules, retry, and fallback."""

    def __init__(
        self,
        registry: ProviderRegistry,
        *,
        default_provider: str,
        rules: tuple[RoutingRule, ...] = (),
        fallback_order: tuple[str, ...] = (),
        max_attempts: int = 2,
        retry_base_delay: float = 1.0,
        retry_sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._registry = registry
        self.default_provider = default_provider
        self.rules = rules
        self.fallback_order = fallback_order
        self.max_attempts = max_attempts
        self.retry_base_delay = retry_base_delay
        self.retry_sleep = retry_sleep

    @property
    def registry(self) -> ProviderRegistry:
        """The underlying provider registry, for callers that need direct provider lookup."""
        return self._registry

    def select(
        self, *, provider: str | None = None, model: str | None = None, hint: str = ""
    ) -> tuple[str, str | None]:
        """Return ``(provider_name, model_override)`` for the given routing inputs.

        ``model_override`` is ``None`` when nothing pinned a model, meaning
        "use whichever provider ends up serving this request's own default
        model".
        """
        if provider:
            return provider, model
        haystack = hint.lower()
        for rule in self.rules:
            if rule.match.lower() in haystack:
                return rule.provider, model or rule.model
        return self.default_provider, model

    def call(
        self,
        build_request: Callable[[str], ChatRequest],
        *,
        provider: str | None = None,
        model: str | None = None,
        hint: str = "",
    ) -> RoutedResponse:
        """Select a provider, call it, retrying transient errors and falling back.

        *build_request* builds the actual :class:`ChatRequest` given the
        model that ended up being used for a particular attempt, so each
        fallback provider gets a request built with its own appropriate
        default model when the caller didn't pin one explicitly. The
        returned :class:`RoutedResponse` reports which registry alias in the
        fallback chain actually served the request.
        """
        provider_name, model_override = self.select(provider=provider, model=model, hint=hint)
        chain = [provider_name, *(p for p in self.fallback_order if p != provider_name)]
        last_error: Exception = ProviderNotFoundError(
            provider_name, available=tuple(self._registry.names())
        )
        for name in chain:
            try:
                candidate = self._registry.require(name)
            except ProviderNotFoundError as exc:
                last_error = exc
                continue
            effective_model = model_override or candidate.model
            request = build_request(effective_model)

            def _call(p: Provider = candidate, r: ChatRequest = request) -> ChatResponse:
                return p.complete(r)

            try:
                response = retry_with_backoff(
                    _call,
                    retry_on=_TRANSIENT_ERRORS,
                    max_attempts=self.max_attempts,
                    base_delay=self.retry_base_delay,
                    sleep=self.retry_sleep,
                )
            except ProviderError as exc:
                last_error = exc
                continue
            return RoutedResponse(response=response, provider_name=name)
        raise last_error
