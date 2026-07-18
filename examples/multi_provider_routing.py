"""Multi-provider routing: route different tasks to different providers/models.

Registers two FakeProvider instances under different names to simulate a
multi-provider setup without needing multiple real API keys -- the same
config shape (routing.rules / routing.fallback_order) works identically
with real providers such as "anthropic".

Run with: python examples/multi_provider_routing.py
"""

from __future__ import annotations

from aiforge.config.schema import AIForgeConfig, EngineConfig, RoutingConfig, RoutingRuleConfig
from aiforge.core.context import TaskRequest
from aiforge.core.engine import Engine
from aiforge.providers.fake import FakeProvider
from aiforge.providers.registry import ProviderRegistry
from aiforge.providers.router import ProviderRouter, RoutingRule
from aiforge.skills.registry import SkillRegistry
from aiforge.skills.resolver import SkillResolver


def main() -> None:
    # Two distinct "providers" -- in a real setup these would be e.g.
    # AnthropicProvider configured with two different models, or a
    # completely different provider implementation for the second one.
    registry = ProviderRegistry()
    registry.register_factory("general", lambda: FakeProvider(model="general-model"))
    registry.register_factory("systems", lambda: FakeProvider(model="systems-model"))

    router = ProviderRouter(
        registry,
        default_provider="general",
        rules=(
            RoutingRule(match="rust", provider="systems", model="systems-model"),
            RoutingRule(match="c++", provider="systems", model="systems-model"),
        ),
        fallback_order=("general", "systems"),
    )
    engine = Engine(router=router, skill_resolver=SkillResolver(SkillRegistry()))

    for prompt in (
        "Write a Python script to parse CSV files.",
        "Write a Rust function using ownership correctly.",
    ):
        result = engine.run(TaskRequest(prompt=prompt))
        print(f"prompt: {prompt!r}")
        print(
            f"  -> routed to provider={result.context.provider_name} model={result.context.model}"
        )

    # The same routing shape, expressed as config (what aiforge.toml looks like):
    config = AIForgeConfig(
        engine=EngineConfig(default_provider="general"),
        routing=RoutingConfig(
            rules=(RoutingRuleConfig(match="rust", provider="systems", model="systems-model"),),
            fallback_order=("general", "systems"),
        ),
    )
    print(f"\nEquivalent aiforge.toml routing config: {config.routing}")


if __name__ == "__main__":
    main()
