"""Quickstart: run AIForge end-to-end with zero API key and zero cost.

Uses the built-in FakeProvider, so this script works out of the box --
useful for a first look at the framework, for CI, and for local development
without spending anything on real Claude calls.

Run with: python examples/quickstart.py
"""

from __future__ import annotations

from aiforge import AIForge
from aiforge.config.schema import AIForgeConfig, EngineConfig


def main() -> None:
    config = AIForgeConfig(engine=EngineConfig(default_provider="fake"))
    forge = AIForge(config=config)

    response = forge.run("Write a Python function that reverses a linked list.")
    print("--- Response ---")
    print(response.text)
    print()
    print(f"provider={response.provider} model={response.model}")
    print(f"tokens={response.usage.total_tokens} cost_usd={response.cost_usd}")

    print()
    print("--- With an explicit skill ---")
    detailed = forge.run_detailed("How do I structure a Flask app?", skills=["python"])
    print(f"resolved skills: {detailed.context.resolved_skills}")
    print(detailed.response.text)

    print()
    print("--- Real Claude ---")
    print("Set ANTHROPIC_API_KEY and switch default_provider to 'anthropic' to see")
    print("this exact same code call real Claude -- nothing else changes.")


if __name__ == "__main__":
    main()
