"""The AIForge facade: the simplest way to use the framework from Python."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator, Sequence
from pathlib import Path

from aiforge.config.loader import load_config
from aiforge.config.schema import AIForgeConfig
from aiforge.core.context import TaskRequest
from aiforge.core.engine import Engine, EngineResult
from aiforge.providers.types import ChatResponse, StreamChunk
from aiforge.utils.async_utils import bounded_gather

__all__ = ["AIForge"]


class AIForge:
    """High-level entry point: load config, build an engine, run tasks."""

    def __init__(
        self, config: AIForgeConfig | None = None, *, config_path: Path | str | None = None
    ) -> None:
        self.config = config if config is not None else load_config(project_path=config_path)
        self.engine = Engine.from_config(self.config)

    def run(
        self,
        prompt: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        skills: Sequence[str] = (),
        system: str | None = None,
        max_tokens: int | None = None,
        file_hints: Sequence[str] = (),
    ) -> ChatResponse:
        """Run *prompt* through the engine and return the provider's response."""
        return self.run_detailed(
            prompt,
            provider=provider,
            model=model,
            skills=skills,
            system=system,
            max_tokens=max_tokens,
            file_hints=file_hints,
        ).response

    def run_detailed(
        self,
        prompt: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        skills: Sequence[str] = (),
        system: str | None = None,
        max_tokens: int | None = None,
        file_hints: Sequence[str] = (),
    ) -> EngineResult:
        """Like :meth:`run`, but returns the full :class:`EngineResult` (response + resolution)."""
        request = TaskRequest(
            prompt=prompt,
            provider=provider,
            model=model,
            skills=tuple(skills),
            system=system,
            max_tokens=max_tokens,
            file_hints=tuple(file_hints),
        )
        return self.engine.run(request)

    def stream(
        self,
        prompt: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        skills: Sequence[str] = (),
        system: str | None = None,
        max_tokens: int | None = None,
        file_hints: Sequence[str] = (),
    ) -> Iterator[StreamChunk]:
        """Stream *prompt* through the engine, yielding incremental chunks."""
        request = TaskRequest(
            prompt=prompt,
            provider=provider,
            model=model,
            skills=tuple(skills),
            system=system,
            max_tokens=max_tokens,
            file_hints=tuple(file_hints),
            stream=True,
        )
        yield from self.engine.stream(request)

    async def astream(
        self,
        prompt: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        skills: Sequence[str] = (),
        system: str | None = None,
        max_tokens: int | None = None,
        file_hints: Sequence[str] = (),
    ) -> AsyncIterator[StreamChunk]:
        """Async variant of :meth:`stream`."""
        request = TaskRequest(
            prompt=prompt,
            provider=provider,
            model=model,
            skills=tuple(skills),
            system=system,
            max_tokens=max_tokens,
            file_hints=tuple(file_hints),
            stream=True,
        )
        async for chunk in self.engine.astream(request):
            yield chunk

    def run_many(self, prompts: Sequence[str], *, concurrency: int = 4) -> list[ChatResponse]:
        """Run multiple independent prompts concurrently (bounded), preserving order."""

        async def _one(prompt: str) -> ChatResponse:
            result = await self.engine.arun(TaskRequest(prompt=prompt))
            return result.response

        async def _run_all() -> list[ChatResponse]:
            return await bounded_gather((_one(p) for p in prompts), limit=concurrency)

        return asyncio.run(_run_all())
