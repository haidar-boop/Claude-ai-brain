"""Async helpers for bounded-concurrency fan-out."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Iterable
from typing import TypeVar

T = TypeVar("T")

__all__ = ["bounded_gather"]


async def bounded_gather(awaitables: Iterable[Awaitable[T]], *, limit: int = 8) -> list[T]:
    """Run *awaitables* concurrently, at most *limit* in flight at once.

    Preserves input order in the returned list, like :func:`asyncio.gather`.
    """
    if limit < 1:
        raise ValueError("limit must be >= 1")
    semaphore = asyncio.Semaphore(limit)

    async def _run(awaitable: Awaitable[T]) -> T:
        async with semaphore:
            return await awaitable

    return await asyncio.gather(*(_run(a) for a in awaitables))
