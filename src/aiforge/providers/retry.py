"""A small, provider-agnostic retry helper with exponential backoff and jitter.

The Anthropic SDK already retries connection errors and 408/409/429/5xx
responses with its own backoff (see ``max_retries``/``timeout`` on the
client) -- this module exists for the provider router's cross-provider
retry-then-fallback logic (see :mod:`aiforge.providers.router`), and as a
reusable utility for custom providers that don't bring their own retry.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable, Sequence
from typing import TypeVar

T = TypeVar("T")

__all__ = ["retry_with_backoff"]


def retry_with_backoff(
    func: Callable[[], T],
    *,
    retry_on: Sequence[type[BaseException]] = (Exception,),
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    jitter: float = 0.25,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call *func*, retrying on exceptions in *retry_on* with exponential backoff.

    Re-raises the triggering exception once *max_attempts* is exhausted.
    *sleep* is injectable so tests don't have to wait in real time.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    for attempt in range(max_attempts):
        try:
            return func()
        except tuple(retry_on):
            if attempt == max_attempts - 1:
                raise
            delay = min(base_delay * (2**attempt), max_delay)
            # Non-cryptographic jitter -- no security implication.
            delay += random.uniform(0, jitter * delay)  # noqa: S311  # nosec B311
            sleep(delay)
    raise AssertionError("unreachable")  # pragma: no cover
