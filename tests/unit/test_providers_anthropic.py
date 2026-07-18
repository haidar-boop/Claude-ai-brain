"""Tests for aiforge.providers.anthropic_provider (Anthropic SDK fully mocked).

No network access and no real ``anthropic`` package behavior is exercised
here -- a minimal fake module is injected into ``sys.modules`` so these
tests run without an API key, matching the "zero-cost to develop/test"
principle used throughout this suite.
"""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from aiforge.core.errors import (
    AIForgeError,
    ProviderAuthError,
    ProviderConnectionError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)
from aiforge.providers.types import ChatRequest, Message, Role


def _request(**overrides: Any) -> ChatRequest:
    defaults: dict[str, Any] = {
        "messages": (Message(role=Role.USER, content="hi"),),
        "model": "claude-opus-4-8",
    }
    defaults.update(overrides)
    return ChatRequest(**defaults)


class _FakeContentBlock:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _FakeUsage:
    def __init__(self, input_tokens: int = 10, output_tokens: int = 5) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_creation_input_tokens = 0
        self.cache_read_input_tokens = 0


class _FakeMessage:
    def __init__(self, text: str = "hello from claude", model: str = "claude-opus-4-8") -> None:
        self.content = [_FakeContentBlock(text)]
        self.usage = _FakeUsage()
        self.model = model
        self.stop_reason = "end_turn"


class _FakeStreamContext:
    def __init__(self, text: str) -> None:
        self._text = text
        self.text_stream = iter([text[: len(text) // 2], text[len(text) // 2 :]] if text else [])

    def __enter__(self) -> _FakeStreamContext:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def get_final_message(self) -> _FakeMessage:
        return _FakeMessage(text=self._text)


class _FakeAsyncStreamContext:
    def __init__(self, text: str) -> None:
        self._text = text
        self._pieces = [text[: len(text) // 2], text[len(text) // 2 :]] if text else []
        self._iter = iter(())

    async def __aenter__(self) -> _FakeAsyncStreamContext:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    @property
    def text_stream(self) -> _FakeAsyncStreamContext:
        self._iter = iter(self._pieces)
        return self

    def __aiter__(self) -> _FakeAsyncStreamContext:
        return self

    async def __anext__(self) -> str:
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration from None

    async def get_final_message(self) -> _FakeMessage:
        return _FakeMessage(text=self._text)


class _FakeMessagesAPI:
    def __init__(self, *, raise_error: Exception | None = None) -> None:
        self._raise_error = raise_error

    def create(self, **kwargs: Any) -> _FakeMessage:
        if self._raise_error is not None:
            raise self._raise_error
        return _FakeMessage(model=kwargs.get("model", "claude-opus-4-8"))

    def stream(self, **kwargs: Any) -> _FakeStreamContext:
        if self._raise_error is not None:
            raise self._raise_error
        return _FakeStreamContext("hello from claude")

    def count_tokens(self, **kwargs: Any) -> _FakeUsage:
        return _FakeUsage(input_tokens=42)


class _FakeAsyncMessagesAPI:
    def __init__(self, *, raise_error: Exception | None = None) -> None:
        self._raise_error = raise_error

    def stream(self, **kwargs: Any) -> _FakeAsyncStreamContext:
        if self._raise_error is not None:
            raise self._raise_error
        return _FakeAsyncStreamContext("hello from claude")


class _FakeClient:
    def __init__(self, *, raise_error: Exception | None = None, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.messages = _FakeMessagesAPI(raise_error=raise_error)


class _FakeAsyncClient:
    def __init__(self, *, raise_error: Exception | None = None, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.messages = _FakeAsyncMessagesAPI(raise_error=raise_error)


def _make_fake_anthropic_module(*, raise_error: Exception | None = None) -> types.ModuleType:
    module = types.ModuleType("anthropic")

    # Mirrors the real SDK's exception MRO (verified against anthropic
    # 0.117.0): AuthenticationError and RateLimitError are APIStatusError
    # subclasses, APITimeoutError is an APIConnectionError subclass, and
    # everything descends from APIError. A flat hierarchy here would let
    # _translate_error's isinstance ordering rot undetected.
    class APIError(Exception):
        pass

    class APIStatusError(APIError):
        pass

    class APIConnectionError(APIError):
        pass

    class AuthenticationError(APIStatusError):
        pass

    class RateLimitError(APIStatusError):
        def __init__(self, message: str) -> None:
            super().__init__(message)
            self.response = types.SimpleNamespace(headers={"retry-after": "5"})

    class APITimeoutError(APIConnectionError):
        pass

    module.APIError = APIError  # type: ignore[attr-defined]
    module.APIStatusError = APIStatusError  # type: ignore[attr-defined]
    module.APIConnectionError = APIConnectionError  # type: ignore[attr-defined]
    module.AuthenticationError = AuthenticationError  # type: ignore[attr-defined]
    module.RateLimitError = RateLimitError  # type: ignore[attr-defined]
    module.APITimeoutError = APITimeoutError  # type: ignore[attr-defined]
    module.Anthropic = lambda **kw: _FakeClient(raise_error=raise_error, **kw)  # type: ignore[attr-defined]
    module.AsyncAnthropic = lambda **kw: _FakeAsyncClient(raise_error=raise_error, **kw)  # type: ignore[attr-defined]
    return module


@pytest.fixture
def fake_anthropic_module(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    module = _make_fake_anthropic_module()
    monkeypatch.setitem(sys.modules, "anthropic", module)
    return module


def _provider_with_error(monkeypatch: pytest.MonkeyPatch, error_name: str, message: str) -> Any:
    module = _make_fake_anthropic_module()
    error = getattr(module, error_name)(message)
    module.Anthropic = lambda **kw: _FakeClient(raise_error=error, **kw)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "anthropic", module)
    from aiforge.providers.anthropic_provider import AnthropicProvider

    return AnthropicProvider()


def test_complete_returns_translated_response(fake_anthropic_module: types.ModuleType) -> None:
    from aiforge.providers.anthropic_provider import AnthropicProvider

    provider = AnthropicProvider()
    response = provider.complete(_request())
    assert response.text == "hello from claude"
    assert response.provider == "anthropic"
    assert response.usage.input_tokens == 10
    assert response.usage.output_tokens == 5
    assert response.stop_reason == "end_turn"
    assert response.cost_usd is None


def test_stream_yields_text_then_final_chunk_with_usage(
    fake_anthropic_module: types.ModuleType,
) -> None:
    from aiforge.providers.anthropic_provider import AnthropicProvider

    provider = AnthropicProvider()
    chunks = list(provider.stream(_request()))
    assert "".join(c.text for c in chunks) == "hello from claude"
    assert chunks[-1].is_final is True
    assert chunks[-1].usage is not None
    assert all(not c.is_final for c in chunks[:-1])


async def test_astream_yields_text_then_final_chunk(
    fake_anthropic_module: types.ModuleType,
) -> None:
    from aiforge.providers.anthropic_provider import AnthropicProvider

    provider = AnthropicProvider()
    chunks = [chunk async for chunk in provider.astream(_request())]
    assert "".join(c.text for c in chunks) == "hello from claude"
    assert chunks[-1].is_final is True


def test_count_tokens_delegates_to_sdk(fake_anthropic_module: types.ModuleType) -> None:
    from aiforge.providers.anthropic_provider import AnthropicProvider

    provider = AnthropicProvider()
    assert provider.count_tokens(_request()) == 42


def test_build_params_includes_system_thinking_and_effort(
    fake_anthropic_module: types.ModuleType,
) -> None:
    from aiforge.providers.anthropic_provider import AnthropicProvider

    provider = AnthropicProvider()
    request = _request(system="be terse", thinking=True, effort="high", temperature=0.5)
    params = provider._build_params(request)
    assert params["system"] == "be terse"
    assert params["thinking"] == {"type": "adaptive"}
    assert params["output_config"] == {"effort": "high"}
    assert params["temperature"] == 0.5


def test_build_params_extra_overrides_are_merged(fake_anthropic_module: types.ModuleType) -> None:
    from aiforge.providers.anthropic_provider import AnthropicProvider

    provider = AnthropicProvider()
    request = _request(extra={"top_p": 0.9})
    params = provider._build_params(request)
    assert params["top_p"] == 0.9


def test_default_model_used_when_request_omits_one(fake_anthropic_module: types.ModuleType) -> None:
    from aiforge.providers.anthropic_provider import DEFAULT_MODEL, AnthropicProvider

    provider = AnthropicProvider(model="claude-haiku-4-5")
    request = _request(model="")
    params = provider._build_params(request)
    assert params["model"] == "claude-haiku-4-5"
    assert DEFAULT_MODEL == "claude-opus-4-8"


def test_auth_error_is_translated(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _provider_with_error(monkeypatch, "AuthenticationError", "bad key")
    with pytest.raises(ProviderAuthError):
        provider.complete(_request())


def test_rate_limit_error_is_translated_with_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _provider_with_error(monkeypatch, "RateLimitError", "slow down")
    with pytest.raises(ProviderRateLimitError) as exc_info:
        provider.complete(_request())
    assert exc_info.value.retry_after == 5.0


def test_timeout_error_is_translated(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _provider_with_error(monkeypatch, "APITimeoutError", "timed out")
    with pytest.raises(ProviderTimeoutError):
        provider.complete(_request())


def test_connection_error_is_translated_to_provider_connection_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A non-timeout network failure (DNS, connection reset) must become a
    # ProviderConnectionError -- previously it leaked as the raw SDK
    # exception, silently bypassing the router's retry AND fallback.
    provider = _provider_with_error(monkeypatch, "APIConnectionError", "connection reset")
    with pytest.raises(ProviderConnectionError):
        provider.complete(_request())


def test_unknown_api_error_is_translated_to_provider_response_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The APIError catch-all: no SDK error type may escape untranslated,
    # so `except AIForgeError` around engine.run() always works.
    provider = _provider_with_error(monkeypatch, "APIError", "something unexpected")
    with pytest.raises(ProviderResponseError):
        provider.complete(_request())


def test_every_translated_error_is_an_aiforge_error(monkeypatch: pytest.MonkeyPatch) -> None:
    for error_name in (
        "AuthenticationError",
        "RateLimitError",
        "APITimeoutError",
        "APIConnectionError",
        "APIStatusError",
        "APIError",
    ):
        provider = _provider_with_error(monkeypatch, error_name, "boom")
        with pytest.raises(AIForgeError):
            provider.complete(_request())


def test_missing_sdk_raises_helpful_import_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "anthropic", None)
    from aiforge.providers.anthropic_provider import AnthropicProvider

    with pytest.raises(ImportError, match="anthropic"):
        AnthropicProvider()
