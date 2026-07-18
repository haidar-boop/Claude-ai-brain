"""Tests for aiforge.providers.cost."""

from __future__ import annotations

import pytest

from aiforge.providers.cost import PRICING, CostTracker, estimate_cost
from aiforge.providers.types import Usage


def test_estimate_cost_known_model() -> None:
    usage = Usage(input_tokens=1_000_000, output_tokens=1_000_000)
    cost = estimate_cost("claude-opus-4-8", usage)
    assert cost == pytest.approx(5.00 + 25.00)


def test_estimate_cost_unknown_model_returns_none() -> None:
    usage = Usage(input_tokens=100, output_tokens=100)
    assert estimate_cost("some-unpriced-model", usage) is None


def test_estimate_cost_includes_cache_write_and_read() -> None:
    usage = Usage(
        input_tokens=0,
        output_tokens=0,
        cache_creation_input_tokens=1_000_000,
        cache_read_input_tokens=1_000_000,
    )
    cost = estimate_cost("claude-opus-4-8", usage)
    pricing = PRICING["claude-opus-4-8"]
    assert cost == pytest.approx(
        (pricing.cache_write_per_million or 0) + (pricing.cache_read_per_million or 0)
    )


def test_pricing_table_cache_multipliers_are_consistent() -> None:
    for model, pricing in PRICING.items():
        if pricing.cache_write_per_million is not None:
            assert pricing.cache_write_per_million == pytest.approx(
                pricing.input_per_million * 1.25
            ), model
        if pricing.cache_read_per_million is not None:
            assert pricing.cache_read_per_million == pytest.approx(
                pricing.input_per_million * 0.1
            ), model


def test_cost_tracker_accumulates_across_calls() -> None:
    tracker = CostTracker()
    usage = Usage(input_tokens=1_000_000, output_tokens=0)
    tracker.record("claude-haiku-4-5", usage)
    tracker.record("claude-haiku-4-5", usage)
    assert tracker.total_usd == pytest.approx(2.00)
    assert tracker.request_count == 2


def test_cost_tracker_record_returns_call_cost() -> None:
    tracker = CostTracker()
    usage = Usage(input_tokens=1_000_000, output_tokens=0)
    cost = tracker.record("claude-haiku-4-5", usage)
    assert cost == pytest.approx(1.00)


def test_cost_tracker_unpriced_model_returns_none_and_does_not_affect_totals() -> None:
    tracker = CostTracker()
    result = tracker.record("unknown-model", Usage(input_tokens=100, output_tokens=100))
    assert result is None
    assert tracker.total_usd == 0.0
    assert tracker.request_count == 0


def test_cost_tracker_by_model_breakdown() -> None:
    tracker = CostTracker()
    tracker.record("claude-haiku-4-5", Usage(input_tokens=1_000_000, output_tokens=0))
    tracker.record("claude-opus-4-8", Usage(input_tokens=1_000_000, output_tokens=0))
    breakdown = tracker.by_model()
    assert breakdown["claude-haiku-4-5"] == pytest.approx(1.00)
    assert breakdown["claude-opus-4-8"] == pytest.approx(5.00)


def test_cost_tracker_by_model_snapshot_is_independent() -> None:
    tracker = CostTracker()
    tracker.record("claude-haiku-4-5", Usage(input_tokens=1_000_000, output_tokens=0))
    snapshot = tracker.by_model()
    snapshot["claude-haiku-4-5"] = 999.0
    assert tracker.by_model()["claude-haiku-4-5"] != 999.0


def test_cost_tracker_reset() -> None:
    tracker = CostTracker()
    tracker.record("claude-haiku-4-5", Usage(input_tokens=1_000_000, output_tokens=0))
    tracker.reset()
    assert tracker.total_usd == 0.0
    assert tracker.request_count == 0
    assert tracker.by_model() == {}
