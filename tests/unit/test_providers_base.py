"""Tests for aiforge.providers.base."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

from aiforge.providers.base import BaseProvider, Provider
from aiforge.providers.types import ChatRequest, ChatResponse, Message, Role, StreamChunk, Usage


def _request() -> ChatRequest:
    return ChatRequest(messages=(Message(role=Role.USER, content="hi"),), model="m")


class _MinimalProvider(BaseProvider):
    name = "minimal"
    model = "minimal-model"

    def complete(self, request: ChatRequest) -> ChatResponse:
        return ChatResponse(
            text="ok",
            model=self.model,
            provider=self.name,
            usage=Usage(input_tokens=1, output_tokens=1),
        )

    def stream(self, request: ChatRequest) -> Iterator[StreamChunk]:
        yield StreamChunk(text="ok", is_final=True)

    async def astream(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        yield StreamChunk(text="ok", is_final=True)

    def count_tokens(self, request: ChatRequest) -> int:
        return 1


def test_minimal_provider_conforms_to_protocol() -> None:
    assert isinstance(_MinimalProvider(), Provider)


async def test_acomplete_default_offloads_to_thread_and_matches_sync() -> None:
    provider = _MinimalProvider()
    sync_response = provider.complete(_request())
    async_response = await provider.acomplete(_request())
    assert sync_response.text == async_response.text
