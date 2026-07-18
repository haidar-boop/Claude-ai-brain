"""Tests for aiforge.providers.retry."""

from __future__ import annotations

import pytest

from aiforge.providers.retry import retry_with_backoff


def test_succeeds_on_first_attempt_without_sleeping() -> None:
    sleeps: list[float] = []
    result = retry_with_backoff(lambda: 42, sleep=sleeps.append)
    assert result == 42
    assert sleeps == []


def test_retries_until_success() -> None:
    attempts = {"count": 0}

    def flaky() -> str:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise ValueError("not yet")
        return "ok"

    sleeps: list[float] = []
    result = retry_with_backoff(
        flaky, retry_on=(ValueError,), max_attempts=5, base_delay=0.01, sleep=sleeps.append
    )
    assert result == "ok"
    assert attempts["count"] == 3
    assert len(sleeps) == 2


def test_exhausts_attempts_and_reraises() -> None:
    def always_fails() -> None:
        raise ValueError("nope")

    sleeps: list[float] = []
    with pytest.raises(ValueError, match="nope"):
        retry_with_backoff(
            always_fails,
            retry_on=(ValueError,),
            max_attempts=3,
            base_delay=0.01,
            sleep=sleeps.append,
        )
    assert len(sleeps) == 2  # slept between 1->2 and 2->3, not after the final failure


def test_does_not_retry_unmatched_exception_types() -> None:
    def raises_type_error() -> None:
        raise TypeError("wrong type")

    sleeps: list[float] = []
    with pytest.raises(TypeError):
        retry_with_backoff(raises_type_error, retry_on=(ValueError,), sleep=sleeps.append)
    assert sleeps == []


def test_backoff_delay_grows_and_respects_max_delay() -> None:
    def always_fails() -> None:
        raise ValueError("nope")

    sleeps: list[float] = []
    with pytest.raises(ValueError):
        retry_with_backoff(
            always_fails,
            retry_on=(ValueError,),
            max_attempts=4,
            base_delay=1.0,
            max_delay=2.5,
            jitter=0.0,
            sleep=sleeps.append,
        )
    # base_delay * 2**attempt for attempts 0,1,2 -> 1, 2, 4, capped at max_delay=2.5
    assert sleeps == [1.0, 2.0, 2.5]


def test_invalid_max_attempts_raises() -> None:
    with pytest.raises(ValueError, match="max_attempts"):
        retry_with_backoff(lambda: None, max_attempts=0)
