"""AnthropicProvider: the official Claude integration.

Imports the ``anthropic`` package lazily (inside ``__init__``), so merely
importing this module -- e.g. while enumerating registered providers for
``aiforge providers list`` -- never requires the ``anthropic`` extra to be
installed. Only actually constructing an :class:`AnthropicProvider` does.

Credentials are read by the Anthropic SDK's own environment resolution
(``ANTHROPIC_API_KEY``, or an ``ant auth login`` profile) -- this class
never hardcodes a key and never reads one from a config file.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Iterator
from typing import Any

from aiforge.core.errors import (
    ProviderAuthError,
    ProviderConnectionError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)
from aiforge.providers.base import BaseProvider
from aiforge.providers.logging import log_request_error, log_request_start, log_response
from aiforge.providers.types import ChatRequest, ChatResponse, StreamChunk, Usage

__all__ = ["DEFAULT_MODEL", "AnthropicProvider"]

DEFAULT_MODEL = "claude-opus-4-8"


class AnthropicProvider(BaseProvider):
    """Claude integration backed by the official ``anthropic`` SDK."""

    name = "anthropic"

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
        base_url: str | None = None,
        max_retries: int = 2,
        timeout: float = 600.0,
    ) -> None:
        try:
            import anthropic
        except ImportError as exc:
            raise ImportError(
                "the 'anthropic' package is required to use AnthropicProvider; "
                "install it with `pip install aiforge[anthropic]`"
            ) from exc

        self._anthropic = anthropic
        self.model = model
        client_kwargs: dict[str, Any] = {"max_retries": max_retries, "timeout": timeout}
        if api_key is not None:
            client_kwargs["api_key"] = api_key
        if base_url is not None:
            client_kwargs["base_url"] = base_url
        self._client = anthropic.Anthropic(**client_kwargs)
        self._async_client = anthropic.AsyncAnthropic(**client_kwargs)

    def complete(self, request: ChatRequest) -> ChatResponse:
        log_request_start(self.name, request)
        started = time.monotonic()
        try:
            raw = self._client.messages.create(**self._build_params(request))
        except Exception as exc:
            translated = self._translate_error(exc)
            log_request_error(self.name, translated, elapsed_s=time.monotonic() - started)
            raise translated from exc
        response = self._to_chat_response(raw)
        log_response(self.name, response, elapsed_s=time.monotonic() - started)
        return response

    def stream(self, request: ChatRequest) -> Iterator[StreamChunk]:
        log_request_start(self.name, request)
        started = time.monotonic()
        params = self._build_params(request)
        try:
            with self._client.messages.stream(**params) as stream:
                for text in stream.text_stream:
                    yield StreamChunk(text=text)
                final = stream.get_final_message()
        except Exception as exc:
            translated = self._translate_error(exc)
            log_request_error(self.name, translated, elapsed_s=time.monotonic() - started)
            raise translated from exc
        response = self._to_chat_response(final)
        log_response(self.name, response, elapsed_s=time.monotonic() - started)
        yield StreamChunk(text="", is_final=True, usage=response.usage)

    async def astream(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        log_request_start(self.name, request)
        started = time.monotonic()
        params = self._build_params(request)
        try:
            async with self._async_client.messages.stream(**params) as stream:
                async for text in stream.text_stream:
                    yield StreamChunk(text=text)
                final = await stream.get_final_message()
        except Exception as exc:
            translated = self._translate_error(exc)
            log_request_error(self.name, translated, elapsed_s=time.monotonic() - started)
            raise translated from exc
        response = self._to_chat_response(final)
        log_response(self.name, response, elapsed_s=time.monotonic() - started)
        yield StreamChunk(text="", is_final=True, usage=response.usage)

    def count_tokens(self, request: ChatRequest) -> int:
        params = self._build_params(request)
        params.pop("max_tokens", None)
        params.pop("stream", None)
        result = self._client.messages.count_tokens(**params)
        return int(result.input_tokens)

    def _build_params(self, request: ChatRequest) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": request.model or self.model,
            "max_tokens": request.max_tokens,
            "messages": [
                {"role": message.role.value, "content": message.content}
                for message in request.messages
            ],
        }
        if request.system:
            params["system"] = request.system
        if request.thinking:
            params["thinking"] = {"type": "adaptive"}
        if request.effort:
            params["output_config"] = {"effort": request.effort}
        if request.temperature is not None:
            params["temperature"] = request.temperature
        params.update(request.extra)
        return params

    def _to_chat_response(self, raw: Any) -> ChatResponse:
        text = "".join(
            block.text for block in raw.content if getattr(block, "type", None) == "text"
        )
        usage = Usage(
            input_tokens=raw.usage.input_tokens,
            output_tokens=raw.usage.output_tokens,
            cache_creation_input_tokens=getattr(raw.usage, "cache_creation_input_tokens", 0) or 0,
            cache_read_input_tokens=getattr(raw.usage, "cache_read_input_tokens", 0) or 0,
        )
        return ChatResponse(
            text=text,
            model=raw.model,
            provider=self.name,
            usage=usage,
            stop_reason=raw.stop_reason,
            cost_usd=None,
            raw=raw,
        )

    def _translate_error(self, exc: Exception) -> Exception:
        # Check order matters: in the real SDK, AuthenticationError and
        # RateLimitError are APIStatusError subclasses, and APITimeoutError is
        # an APIConnectionError subclass -- narrow types must be tested before
        # their bases. The trailing APIError catch-all guarantees no SDK
        # exception ever escapes untranslated, which ProviderRouter's
        # retry/fallback (and callers' `except AIForgeError`) depend on.
        anthropic = self._anthropic
        if isinstance(exc, anthropic.AuthenticationError):
            return ProviderAuthError(str(exc))
        if isinstance(exc, anthropic.RateLimitError):
            return ProviderRateLimitError(str(exc), retry_after=_parse_retry_after(exc))
        if isinstance(exc, anthropic.APITimeoutError):
            return ProviderTimeoutError(str(exc))
        if isinstance(exc, anthropic.APIConnectionError):
            return ProviderConnectionError(str(exc))
        if isinstance(exc, anthropic.APIStatusError):
            return ProviderResponseError(str(exc))
        if isinstance(exc, anthropic.APIError):
            return ProviderResponseError(str(exc))
        return exc


def _parse_retry_after(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    value = headers.get("retry-after")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
