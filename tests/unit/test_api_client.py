"""Tests for aiforge.api.client."""

from __future__ import annotations

from pathlib import Path

from aiforge.api.client import AIForge
from aiforge.config.schema import AIForgeConfig, EngineConfig


def _forge() -> AIForge:
    return AIForge(config=AIForgeConfig(engine=EngineConfig(default_provider="fake")))


def test_run_returns_text_response() -> None:
    forge = _forge()
    response = forge.run("hello")
    assert response.provider == "fake"
    assert response.text


def test_run_detailed_returns_engine_result() -> None:
    forge = _forge()
    result = forge.run_detailed("hello")
    assert result.response.provider == "fake"
    assert result.context.provider_name == "fake"


def test_stream_yields_chunks() -> None:
    forge = _forge()
    chunks = list(forge.stream("hello"))
    assert chunks[-1].is_final is True


async def test_astream_yields_chunks() -> None:
    forge = _forge()
    chunks = [c async for c in forge.astream("hello")]
    assert chunks[-1].is_final is True


def test_run_many_preserves_order() -> None:
    forge = _forge()
    responses = forge.run_many(["first", "second", "third"])
    assert len(responses) == 3
    assert "first" in responses[0].text
    assert "second" in responses[1].text
    assert "third" in responses[2].text


def test_run_with_explicit_provider_and_model_override() -> None:
    forge = _forge()
    response = forge.run("hello", provider="fake", model="custom-model")
    assert response.model == "custom-model"


def test_config_defaults_when_not_passed(tmp_path: Path) -> None:
    # AIForge() with no explicit config falls back to load_config()'s shipped
    # defaults -- point at a directory with no aiforge.toml so this only
    # exercises defaults.toml, not a stray project file.
    forge = AIForge(config_path=tmp_path / "aiforge.toml")
    assert forge.config.engine.default_provider == "anthropic"
