"""Token-usage cost tracking with a pluggable, easily-updated pricing table."""

from __future__ import annotations

import threading
from dataclasses import dataclass

from aiforge.providers.types import Usage

__all__ = ["PRICING", "CostTracker", "ModelPricing", "estimate_cost"]


@dataclass(frozen=True, slots=True)
class ModelPricing:
    """USD price per million tokens for a given model."""

    input_per_million: float
    output_per_million: float
    cache_write_per_million: float | None = None
    cache_read_per_million: float | None = None


# Pricing snapshot in USD per 1,000,000 tokens -- update as providers change
# theirs. Cache write/read figures follow Anthropic's published multipliers
# (1.25x input for a 5-minute-TTL cache write, 0.1x input for a cache read)
# where a model-specific figure isn't separately published. Sonnet 5 has a
# temporary introductory price ($2/$10) through 2026-08-31; the table uses
# the standard post-introductory price ($3/$15) since it's the durable value.
PRICING: dict[str, ModelPricing] = {
    "claude-opus-4-8": ModelPricing(5.00, 25.00, 6.25, 0.50),
    "claude-opus-4-7": ModelPricing(5.00, 25.00, 6.25, 0.50),
    "claude-opus-4-6": ModelPricing(5.00, 25.00, 6.25, 0.50),
    "claude-opus-4-5": ModelPricing(5.00, 25.00, 6.25, 0.50),
    "claude-sonnet-5": ModelPricing(3.00, 15.00, 3.75, 0.30),
    "claude-sonnet-4-6": ModelPricing(3.00, 15.00, 3.75, 0.30),
    "claude-sonnet-4-5": ModelPricing(3.00, 15.00, 3.75, 0.30),
    "claude-haiku-4-5": ModelPricing(1.00, 5.00, 1.25, 0.10),
    "claude-fable-5": ModelPricing(10.00, 50.00, 12.50, 1.00),
}


def estimate_cost(model: str, usage: Usage) -> float | None:
    """Return the estimated USD cost of *usage* for *model*, or ``None`` if unpriced.

    Token counts come from the provider's wire response and are not trusted:
    negative values are clamped to zero (a hostile or buggy endpoint must not
    drive the spend ledger negative), and values too large for float
    arithmetic yield ``None`` rather than letting ``OverflowError`` escape
    from the engine's post-response cost accounting.
    """
    pricing = PRICING.get(model)
    if pricing is None:
        return None
    input_tokens = max(0, usage.input_tokens)
    output_tokens = max(0, usage.output_tokens)
    cache_write_tokens = max(0, usage.cache_creation_input_tokens)
    cache_read_tokens = max(0, usage.cache_read_input_tokens)
    try:
        cost = (
            input_tokens * pricing.input_per_million + output_tokens * pricing.output_per_million
        ) / 1_000_000
        if cache_write_tokens and pricing.cache_write_per_million is not None:
            cost += cache_write_tokens * pricing.cache_write_per_million / 1_000_000
        if cache_read_tokens and pricing.cache_read_per_million is not None:
            cost += cache_read_tokens * pricing.cache_read_per_million / 1_000_000
    except OverflowError:
        return None
    return cost


class CostTracker:
    """Accumulates estimated spend across requests, thread-safely."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._total_usd = 0.0
        self._request_count = 0
        self._by_model: dict[str, float] = {}

    def record(self, model: str, usage: Usage) -> float | None:
        """Estimate and accumulate the cost of *usage* for *model*.

        Returns the estimated cost for this single call, or ``None`` if
        *model* isn't in the pricing table -- the running totals are
        unaffected in that case.
        """
        cost = estimate_cost(model, usage)
        if cost is None:
            return None
        with self._lock:
            self._total_usd += cost
            self._request_count += 1
            self._by_model[model] = self._by_model.get(model, 0.0) + cost
        return cost

    @property
    def total_usd(self) -> float:
        with self._lock:
            return self._total_usd

    @property
    def request_count(self) -> int:
        with self._lock:
            return self._request_count

    def by_model(self) -> dict[str, float]:
        """Return a snapshot of accumulated cost per model."""
        with self._lock:
            return dict(self._by_model)

    def reset(self) -> None:
        with self._lock:
            self._total_usd = 0.0
            self._request_count = 0
            self._by_model.clear()
