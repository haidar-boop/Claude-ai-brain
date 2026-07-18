"""Typed exception hierarchy for AIForge.

Every exception inherits from :class:`AIForgeError`, so callers that don't
care about the specific failure mode can catch broadly. Cross-cutting bases
like :class:`RegistryError` are additionally mixed into the "not found"
errors of specific domains, so ``except RegistryError`` catches *any*
not-found error (provider or skill) without also catching unrelated domain
errors such as a rate limit or a validation failure.
"""

from __future__ import annotations

__all__ = [
    "AIForgeError",
    "ConfigError",
    "ConfigValidationError",
    "EngineError",
    "ProviderAuthError",
    "ProviderError",
    "ProviderNotFoundError",
    "ProviderRateLimitError",
    "ProviderResponseError",
    "ProviderTimeoutError",
    "RegistryError",
    "SkillConflictError",
    "SkillError",
    "SkillNotFoundError",
    "SkillValidationError",
]


class AIForgeError(Exception):
    """Base class for every exception raised by AIForge."""


class ConfigError(AIForgeError):
    """Raised for configuration loading or validation problems."""


class ConfigValidationError(ConfigError):
    """Raised when a configuration value fails schema validation."""


class RegistryError(AIForgeError):
    """Raised for registry lookup/registration problems."""


class EngineError(AIForgeError):
    """Raised for engine-level orchestration failures."""


class ProviderError(AIForgeError):
    """Base class for AI-provider related errors."""


class ProviderNotFoundError(ProviderError, RegistryError):
    """Raised when a requested provider name is not registered."""

    def __init__(self, name: str, *, available: tuple[str, ...] = ()) -> None:
        message = f"no provider registered as {name!r}"
        if available:
            message += f" (available: {', '.join(sorted(available))})"
        super().__init__(message)
        self.name = name
        self.available = available


class ProviderAuthError(ProviderError):
    """Raised when a provider rejects credentials (missing or invalid key)."""


class ProviderRateLimitError(ProviderError):
    """Raised when a provider's rate limit is exceeded."""

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ProviderTimeoutError(ProviderError):
    """Raised when a provider request exceeds its configured timeout."""


class ProviderResponseError(ProviderError):
    """Raised when a provider returns an unexpected or invalid response."""


class SkillError(AIForgeError):
    """Base class for skill-system errors."""


class SkillNotFoundError(SkillError, RegistryError):
    """Raised when a requested skill name is not registered."""

    def __init__(self, name: str, *, available: tuple[str, ...] = ()) -> None:
        message = f"no skill registered as {name!r}"
        if available:
            message += f" (available: {', '.join(sorted(available))})"
        super().__init__(message)
        self.name = name
        self.available = available


class SkillValidationError(SkillError):
    """Raised when a skill manifest fails schema validation."""

    def __init__(self, message: str, *, source: str | None = None) -> None:
        super().__init__(f"{source}: {message}" if source else message)
        self.source = source


class SkillConflictError(SkillError):
    """Raised when two enabled skills declare an unresolved hard conflict."""

    def __init__(self, message: str, *, skills: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.skills = skills
