"""Tests for aiforge.providers.types."""

from __future__ import annotations

from aiforge.providers.types import ChatRequest, ChatResponse, Message, Role, StreamChunk, Usage


def test_role_is_a_plain_string() -> None:
    assert Role.USER == "user"
    assert str(Role.ASSISTANT) == "assistant"


def test_message_holds_role_and_content() -> None:
    message = Message(role=Role.USER, content="hi")
    assert message.role == Role.USER
    assert message.content == "hi"


def test_chat_request_defaults() -> None:
    request = ChatRequest(messages=(Message(role=Role.USER, content="hi"),), model="m")
    assert request.max_tokens == 4096
    assert request.system is None
    assert request.stream is False
    assert request.temperature is None
    assert request.thinking is False
    assert request.effort is None
    assert request.extra == {}


def test_chat_request_extra_defaults_are_independent() -> None:
    a = ChatRequest(messages=(), model="m")
    b = ChatRequest(messages=(), model="m")
    a.extra["x"] = 1
    assert b.extra == {}


def test_usage_total_tokens() -> None:
    usage = Usage(input_tokens=10, output_tokens=5)
    assert usage.total_tokens == 15


def test_usage_defaults_cache_fields_to_zero() -> None:
    usage = Usage(input_tokens=1, output_tokens=1)
    assert usage.cache_creation_input_tokens == 0
    assert usage.cache_read_input_tokens == 0


def test_chat_response_defaults() -> None:
    response = ChatResponse(
        text="hi", model="m", provider="fake", usage=Usage(input_tokens=1, output_tokens=1)
    )
    assert response.stop_reason is None
    assert response.cost_usd is None
    assert response.raw is None


def test_stream_chunk_defaults() -> None:
    chunk = StreamChunk(text="hello")
    assert chunk.is_final is False
    assert chunk.usage is None
