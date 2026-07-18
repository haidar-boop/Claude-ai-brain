"""The Engine: orchestrates configuration, skill resolution, and provider calls.

This is the framework's single integration point -- it depends on the
provider layer, the skill layer, and the config schema, but none of those
layers depend on it or on each other. Every collaborator is passed in
(constructor injection), so the engine itself is testable with fakes for
all three (see :mod:`aiforge.providers.fake`).
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass

from aiforge.config.schema import AIForgeConfig
from aiforge.core.context import TaskContext, TaskRequest
from aiforge.core.events import EventBus
from aiforge.providers.cost import CostTracker
from aiforge.providers.registry import ProviderRegistry
from aiforge.providers.router import ProviderRouter, RoutingRule
from aiforge.providers.types import ChatRequest, ChatResponse, Message, Role, StreamChunk
from aiforge.skills.loader import discover_skills
from aiforge.skills.registry import SkillRegistry
from aiforge.skills.resolver import ResolvedSkills, SkillResolver

__all__ = ["Engine", "EngineResult"]


@dataclass(frozen=True, slots=True)
class EngineResult:
    """A completed run: the provider response plus what the engine resolved to get there."""

    response: ChatResponse
    context: TaskContext


class Engine:
    """Orchestrates skill resolution and provider calls for a task."""

    def __init__(
        self,
        *,
        router: ProviderRouter,
        skill_resolver: SkillResolver,
        cost_tracker: CostTracker | None = None,
        events: EventBus | None = None,
        base_system: str | None = None,
    ) -> None:
        self.router = router
        self.skill_resolver = skill_resolver
        self.cost_tracker = cost_tracker or CostTracker()
        self.events = events or EventBus()
        self.base_system = base_system

    @classmethod
    def from_config(cls, config: AIForgeConfig, *, base_system: str | None = None) -> Engine:
        """Build a fully-wired :class:`Engine` from an :class:`AIForgeConfig`.

        Discovers providers (entry points) and skills (built-in directory +
        configured extra directories + entry points), applies config policy
        to both, and wires up routing rules and fallback order. This is the
        one place that touches every layer -- everything it builds is still
        plain constructor injection underneath.
        """
        provider_registry = ProviderRegistry()
        provider_registry.discover_entry_points()

        skill_registry = SkillRegistry()
        skill_registry.register_all(discover_skills(extra_dirs=config.skills.extra_dirs))
        skill_registry.apply_policy(enabled=config.skills.enabled, disabled=config.skills.disabled)

        router = ProviderRouter(
            provider_registry,
            default_provider=config.engine.default_provider,
            rules=tuple(
                RoutingRule(match=r.match, provider=r.provider, model=r.model)
                for r in config.routing.rules
            ),
            fallback_order=config.routing.fallback_order,
            max_attempts=config.routing.max_attempts,
        )
        return cls(
            router=router, skill_resolver=SkillResolver(skill_registry), base_system=base_system
        )

    def run(self, request: TaskRequest) -> EngineResult:
        """Resolve skills, call a provider (with retry/fallback), and return the result."""
        resolved, system, build_request = self._prepare(request)
        self.events.emit("engine.request_started", skills=[m.name for m in resolved.selected])
        routed = self.router.call(
            build_request, provider=request.provider, model=request.model, hint=request.prompt
        )
        response = self._track_cost(routed.response)
        context = TaskContext(
            request=request,
            provider_name=routed.provider_name,
            model=response.model,
            resolved_skills=tuple(m.name for m in resolved.selected),
            composed_system=system,
        )
        self.events.emit(
            "engine.request_completed", provider=routed.provider_name, model=response.model
        )
        return EngineResult(response=response, context=context)

    async def arun(self, request: TaskRequest) -> EngineResult:
        """Async variant of :meth:`run` (offloads the sync pipeline to a thread)."""
        return await asyncio.to_thread(self.run, request)

    def stream(self, request: TaskRequest) -> Iterator[StreamChunk]:
        """Resolve skills and stream a single provider's response.

        Unlike :meth:`run`, streaming does not retry or fall back: once
        output has started reaching the caller, silently restarting on a
        different provider would produce a corrupted or duplicated stream.
        """
        _, _, chat_request = self._prepare_streaming(request)
        provider_name, model = self.router.select(
            provider=request.provider, model=request.model, hint=request.prompt
        )
        provider = self.router.registry.require(provider_name)
        chat_request = dataclasses.replace(chat_request, model=model or provider.model)
        for chunk in provider.stream(chat_request):
            if chunk.is_final and chunk.usage is not None:
                self.cost_tracker.record(chat_request.model, chunk.usage)
            yield chunk

    async def astream(self, request: TaskRequest) -> AsyncIterator[StreamChunk]:
        """Async variant of :meth:`stream`."""
        _, _, chat_request = self._prepare_streaming(request)
        provider_name, model = self.router.select(
            provider=request.provider, model=request.model, hint=request.prompt
        )
        provider = self.router.registry.require(provider_name)
        chat_request = dataclasses.replace(chat_request, model=model or provider.model)
        async for chunk in provider.astream(chat_request):
            if chunk.is_final and chunk.usage is not None:
                self.cost_tracker.record(chat_request.model, chunk.usage)
            yield chunk

    def _prepare(
        self, request: TaskRequest
    ) -> tuple[ResolvedSkills, str | None, Callable[[str], ChatRequest]]:
        resolved = self.skill_resolver.resolve(
            explicit=request.skills, prompt=request.prompt, file_hints=request.file_hints
        )
        system = _compose_system(self.base_system, request.system, resolved.composed_guidance)

        def build_request(model: str) -> ChatRequest:
            return ChatRequest(
                messages=(Message(role=Role.USER, content=request.prompt),),
                model=model,
                max_tokens=request.max_tokens or 4096,
                system=system,
                stream=request.stream,
            )

        return resolved, system, build_request

    def _prepare_streaming(
        self, request: TaskRequest
    ) -> tuple[ResolvedSkills, str | None, ChatRequest]:
        resolved, system, build_request = self._prepare(request)
        # model is filled in by the caller once the provider is selected;
        # "" is a harmless placeholder immediately replaced via dataclasses.replace.
        chat_request = dataclasses.replace(build_request(""), stream=True)
        return resolved, system, chat_request

    def _track_cost(self, response: ChatResponse) -> ChatResponse:
        cost = self.cost_tracker.record(response.model, response.usage)
        if cost is None:
            return response
        return dataclasses.replace(response, cost_usd=cost)


def _compose_system(*parts: str | None) -> str | None:
    joined = "\n\n".join(p for p in parts if p)
    return joined or None
