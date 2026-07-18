"""Tests for aiforge.providers.fake."""

from __future__ import annotations

import pytest

from aiforge.core.errors import ProviderRateLimitError
from aiforge.providers.base import Provider
from aiforge.providers.fake import FakeProvider
from aiforge.providers.types import ChatRequest, Message, Role


def _request(prompt: str = "hello") -> ChatRequest:
    return ChatRequest(messages=(Message(role=Role.USER, content=prompt),), model="fake-model")


def test_conforms_to_provider_protocol() -> None:
    assert isinstance(FakeProvider(), Provider)


def test_complete_returns_deterministic_response() -> None:
    provider = FakeProvider()
    response = provider.complete(_request("hi there"))
    assert "hi there" in response.text
    assert response.provider == "fake"
    assert response.model == "fake-model"
    assert response.stop_reason == "end_turn"
    assert response.usage.input_tokens > 0
    assert response.usage.output_tokens > 0


def test_complete_uses_custom_respond_fn() -> None:
    provider = FakeProvider(respond_fn=lambda request: "canned reply")
    response = provider.complete(_request())
    assert response.text == "canned reply"


def test_stream_reassembles_to_same_text_as_complete() -> None:
    provider = FakeProvider(respond_fn=lambda request: "a longer canned response to chunk up")
    complete_text = provider.complete(_request()).text
    stream_text = "".join(c.text for c in provider.stream(_request()))
    assert stream_text == complete_text


def test_stream_last_chunk_is_final_with_usage() -> None:
    provider = FakeProvider()
    chunks = list(provider.stream(_request()))
    assert chunks[-1].is_final is True
    assert chunks[-1].usage is not None
    assert all(not c.is_final for c in chunks[:-1])


async def test_astream_matches_sync_stream() -> None:
    provider = FakeProvider(respond_fn=lambda request: "same text")
    sync_chunks = [c.text for c in provider.stream(_request())]
    async_chunks = [c.text async for c in provider.astream(_request())]
    assert sync_chunks == async_chunks


async def test_acomplete_matches_sync_complete() -> None:
    provider = FakeProvider(respond_fn=lambda request: "same text")
    sync_response = provider.complete(_request())
    async_response = await provider.acomplete(_request())
    assert sync_response.text == async_response.text


def test_count_tokens_is_positive_for_nonempty_prompt() -> None:
    provider = FakeProvider()
    assert provider.count_tokens(_request("some prompt text")) > 0


def test_fail_times_raises_then_recovers() -> None:
    provider = FakeProvider(fail_times=2)
    with pytest.raises(ProviderRateLimitError):
        provider.complete(_request())
    with pytest.raises(ProviderRateLimitError):
        provider.complete(_request())
    response = provider.complete(_request())
    assert response.text


def test_custom_fail_error_is_raised_verbatim() -> None:
    custom_error = ValueError("custom failure")
    provider = FakeProvider(fail_times=1, fail_error=custom_error)
    with pytest.raises(ValueError, match="custom failure"):
        provider.complete(_request())


def test_empty_prompt_still_produces_response() -> None:
    provider = FakeProvider()
    response = provider.complete(_request(""))
    assert response.text
