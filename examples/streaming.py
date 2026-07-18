"""Streaming: incrementally print a response as it arrives.

Uses the built-in FakeProvider, so this runs with zero API key and zero
cost; switch the config's default_provider to "anthropic" (with
ANTHROPIC_API_KEY set) to see this same code stream real Claude output.

Run with: python examples/streaming.py
"""

from __future__ import annotations

from aiforge import AIForge
from aiforge.config.schema import AIForgeConfig, EngineConfig


def main() -> None:
    config = AIForgeConfig(engine=EngineConfig(default_provider="fake"))
    forge = AIForge(config=config)

    print("Streaming response:\n")
    total_tokens = 0
    for chunk in forge.stream("Explain what a linked list is, in three sentences."):
        print(chunk.text, end="", flush=True)
        if chunk.is_final and chunk.usage is not None:
            total_tokens = chunk.usage.total_tokens
    print(f"\n\n[stream complete -- {total_tokens} tokens]")


if __name__ == "__main__":
    main()
