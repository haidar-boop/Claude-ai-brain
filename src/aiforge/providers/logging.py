"""Request/response debug logging for provider implementations."""

from __future__ import annotations

from aiforge.providers.types import ChatRequest, ChatResponse
from aiforge.utils.logging import get_logger, redact

__all__ = ["log_request_error", "log_request_start", "log_response"]

_logger = get_logger(__name__)


def log_request_start(provider: str, request: ChatRequest) -> None:
    """Log that *provider* is about to send *request*.

    Debug-level only (enable with ``AIFORGE_LOG_LEVEL=DEBUG``); logs shape,
    never message content, to avoid leaking prompts into logs by default.
    """
    _logger.debug(
        "provider request started",
        extra={
            "extra_fields": redact(
                {
                    "provider": provider,
                    "model": request.model,
                    "message_count": len(request.messages),
                    "max_tokens": request.max_tokens,
                    "stream": request.stream,
                }
            )
        },
    )


def log_response(provider: str, response: ChatResponse, *, elapsed_s: float) -> None:
    """Log that *provider* returned *response* after *elapsed_s* seconds."""
    _logger.debug(
        "provider request completed",
        extra={
            "extra_fields": {
                "provider": provider,
                "model": response.model,
                "stop_reason": response.stop_reason,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "cost_usd": response.cost_usd,
                "elapsed_s": round(elapsed_s, 4),
            }
        },
    )


def log_request_error(provider: str, error: Exception, *, elapsed_s: float) -> None:
    """Log that *provider*'s request failed with *error* after *elapsed_s* seconds."""
    _logger.debug(
        "provider request failed",
        extra={
            "extra_fields": {
                "provider": provider,
                "error_type": type(error).__name__,
                "error": str(error),
                "elapsed_s": round(elapsed_s, 4),
            }
        },
    )
