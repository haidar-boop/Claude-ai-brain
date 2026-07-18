"""Tests for aiforge.utils.async_utils."""

from __future__ import annotations

import asyncio

import pytest

from aiforge.utils.async_utils import bounded_gather


async def test_bounded_gather_preserves_order() -> None:
    async def identity(x: int) -> int:
        await asyncio.sleep(0)
        return x

    result = await bounded_gather([identity(i) for i in range(10)], limit=3)
    assert result == list(range(10))


async def test_bounded_gather_respects_limit() -> None:
    in_flight = 0
    max_in_flight = 0
    lock = asyncio.Lock()

    async def track(x: int) -> int:
        nonlocal in_flight, max_in_flight
        async with lock:
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0.01)
        async with lock:
            in_flight -= 1
        return x

    await bounded_gather([track(i) for i in range(20)], limit=4)
    assert max_in_flight <= 4


async def test_bounded_gather_propagates_exceptions() -> None:
    async def boom() -> int:
        raise ValueError("boom")

    async def ok() -> int:
        return 1

    with pytest.raises(ValueError, match="boom"):
        await bounded_gather([ok(), boom()], limit=2)


def test_bounded_gather_rejects_invalid_limit() -> None:
    async def run() -> None:
        await bounded_gather([], limit=0)

    with pytest.raises(ValueError, match="limit"):
        asyncio.run(run())
