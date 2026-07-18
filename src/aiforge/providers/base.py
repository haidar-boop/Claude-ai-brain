"""Provider protocol and shared base implementation."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterator
from typing import Protocol, runtime_checkable

from aiforge.providers.types import ChatRequest, ChatResponse, StreamChunk

__all__ = ["BaseProvider", "Provider"]


@runtime_checkable
class Provider(Protocol):
    """The contract every AI provider implementation must satisfy."""

    name: str
    model: str

    def complete(self, request: ChatRequest) -> ChatResponse:
        """Run a single, non-streaming completion."""
        ...

    def stream(self, request: ChatRequest) -> Iterator[StreamChunk]:
        """Run a streaming completion, yielding incremental chunks."""
        ...

    async def acomplete(self, request: ChatRequest) -> ChatResponse:
        """Async completion."""
        ...

    def astream(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        """Run an async streaming completion, yielding incremental chunks."""
        ...

    def count_tokens(self, request: ChatRequest) -> int:
        """Return the provider's own token count for *request* (input side)."""
        ...


class BaseProvider(ABC):
    """Shared scaffolding for concrete providers.

    Supplies a generic thread-offloaded default for :meth:`acomplete` only.
    Every other method is provider-specific and must be implemented
    directly: there is no safe generic way to turn a synchronous streaming
    generator into a real async one without either blocking the event loop
    or building a thread+queue bridge with its own cancellation edge cases,
    so each provider implements native async streaming instead.
    """

    name: str
    model: str

    @abstractmethod
    def complete(self, request: ChatRequest) -> ChatResponse:
        """Run a single, non-streaming completion."""

    @abstractmethod
    def stream(self, request: ChatRequest) -> Iterator[StreamChunk]:
        """Run a streaming completion, yielding incremental chunks."""

    async def acomplete(self, request: ChatRequest) -> ChatResponse:
        """Async completion. Default: offload the sync :meth:`complete` to a thread."""
        return await asyncio.to_thread(self.complete, request)

    @abstractmethod
    def astream(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        """Run an async streaming completion, yielding incremental chunks."""

    @abstractmethod
    def count_tokens(self, request: ChatRequest) -> int:
        """Return the provider's own token count for *request* (input side)."""
