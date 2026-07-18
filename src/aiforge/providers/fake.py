"""FakeProvider: a deterministic, zero-network, zero-cost provider.

Used by the test suite, the examples, and local development so the full
engine pipeline (config -> skill resolution -> provider call -> cost
tracking) can be exercised without an API key or spending a cent. It ships
under the ``fake`` entry point like any other provider, or can be
constructed directly.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Iterator

from aiforge.core.errors import ProviderRateLimitError
from aiforge.providers.base import BaseProvider
from aiforge.providers.types import ChatRequest, ChatResponse, StreamChunk, Usage

__all__ = ["FakeProvider"]

DEFAULT_RESPONSE_TEMPLATE = "This is a response from the fake provider for: {prompt}"


class FakeProvider(BaseProvider):
    """A fully in-memory :class:`~aiforge.providers.base.Provider` implementation."""

    name = "fake"

    def __init__(
        self,
        *,
        model: str = "fake-model",
        respond_fn: Callable[[ChatRequest], str] | None = None,
        stream_chunk_size: int = 12,
        fail_times: int = 0,
        fail_error: Exception | None = None,
    ) -> None:
        self.model = model
        self._respond_fn = respond_fn or self._default_respond
        self._stream_chunk_size = stream_chunk_size
        self._fail_times = fail_times
        self._fail_error = fail_error
        self._call_count = 0

    @staticmethod
    def _default_respond(request: ChatRequest) -> str:
        prompt = next((m.content for m in reversed(request.messages) if m.content), "")
        return DEFAULT_RESPONSE_TEMPLATE.format(prompt=prompt.strip()[:200])

    def _maybe_fail(self) -> None:
        self._call_count += 1
        if self._call_count <= self._fail_times:
            raise self._fail_error or ProviderRateLimitError(
                "fake provider simulated rate limit", retry_after=0.0
            )

    def _build_response(self, request: ChatRequest) -> ChatResponse:
        text = self._respond_fn(request)
        usage = Usage(
            input_tokens=_estimate_tokens(request),
            output_tokens=_estimate_tokens_str(text),
        )
        return ChatResponse(
            text=text,
            model=request.model or self.model,
            provider=self.name,
            usage=usage,
            stop_reason="end_turn",
            cost_usd=None,
        )

    def complete(self, request: ChatRequest) -> ChatResponse:
        self._maybe_fail()
        return self._build_response(request)

    def stream(self, request: ChatRequest) -> Iterator[StreamChunk]:
        self._maybe_fail()
        response = self._build_response(request)
        for piece in _chunk_text(response.text, self._stream_chunk_size):
            yield StreamChunk(text=piece)
        yield StreamChunk(text="", is_final=True, usage=response.usage)

    async def astream(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        for chunk in self.stream(request):
            yield chunk
            await asyncio.sleep(0)

    def count_tokens(self, request: ChatRequest) -> int:
        return _estimate_tokens(request)


def _estimate_tokens(request: ChatRequest) -> int:
    text = " ".join(m.content for m in request.messages)
    if request.system:
        text = f"{request.system} {text}"
    return _estimate_tokens_str(text)


def _estimate_tokens_str(text: str) -> int:
    # A rough, deterministic ~4-chars/token approximation -- good enough for
    # exercising cost-tracking and usage-reporting code paths in tests
    # without pulling in a real tokenizer.
    return max(1, len(text) // 4)


def _chunk_text(text: str, size: int) -> Iterator[str]:
    if not text:
        return
    for start in range(0, len(text), size):
        yield text[start : start + size]
