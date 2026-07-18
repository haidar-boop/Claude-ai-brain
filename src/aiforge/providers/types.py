"""Provider-neutral request/response types.

These types are the contract between :mod:`aiforge.core.engine` and any
:class:`~aiforge.providers.base.Provider` implementation. The engine never
imports an SDK type directly; each provider is responsible for translating
to/from its own SDK's shapes at the boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

__all__ = ["ChatRequest", "ChatResponse", "Message", "Role", "StreamChunk", "Usage"]


class Role(StrEnum):
    """Conversation participant role."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class Message:
    """A single conversation turn."""

    role: Role
    content: str


@dataclass(slots=True)
class ChatRequest:
    """A provider-neutral chat completion request."""

    messages: tuple[Message, ...]
    model: str
    max_tokens: int = 4096
    system: str | None = None
    stream: bool = False
    temperature: float | None = None
    thinking: bool = False
    """Whether to request extended/adaptive reasoning, if the provider and
    model support it. Providers that don't support this silently ignore it."""
    effort: str | None = None
    """Reasoning effort hint (e.g. "low"/"medium"/"high"/"xhigh"/"max" for
    Claude). Providers that don't support this silently ignore it."""
    extra: dict[str, Any] = field(default_factory=dict)
    """Provider-specific passthrough parameters not covered by the neutral
    fields above; merged into the provider's native request last."""


@dataclass(frozen=True, slots=True)
class Usage:
    """Token usage for a single request."""

    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True, slots=True)
class ChatResponse:
    """A provider-neutral chat completion response."""

    text: str
    model: str
    provider: str
    usage: Usage
    stop_reason: str | None = None
    cost_usd: float | None = None
    """Estimated USD cost, populated centrally by
    :class:`aiforge.providers.cost.CostTracker` (via the engine), not by the
    provider itself -- ``None`` means no pricing data is available for
    *model*, not that the call was necessarily free."""
    raw: Any = None
    """The provider SDK's raw response object, for callers that need
    provider-specific details the neutral fields don't model."""


@dataclass(frozen=True, slots=True)
class StreamChunk:
    """A single incremental piece of a streamed response.

    Providers yield zero or more chunks with ``is_final=False`` (incremental
    text, ``usage=None``), followed by exactly one trailing chunk with
    ``is_final=True`` carrying an empty string and the completed
    :class:`Usage`. Consumers that only care about the assembled text can
    ignore ``is_final``/``usage`` entirely and just concatenate ``.text``.
    """

    text: str
    is_final: bool = False
    usage: Usage | None = None
