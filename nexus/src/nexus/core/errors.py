"""Typed exception hierarchy for Nexus.

Every exception raised by Nexus inherits from :class:`NexusError`, so
callers that don't care about the specific failure mode can catch broadly
without also swallowing unrelated bugs (``KeyError``, ``AttributeError``,
...). Service-level "not found" and "invalid input" cases get their own
types because the UI and the REST API map them to distinct user-facing
outcomes (a dialog vs. a 404 vs. a 400).
"""

from __future__ import annotations

__all__ = [
    "AIError",
    "ApiError",
    "AutomationError",
    "ConfigError",
    "DatabaseError",
    "ExportError",
    "MigrationError",
    "NexusError",
    "NotFoundError",
    "PluginError",
    "ServiceError",
    "ValidationError",
]


class NexusError(Exception):
    """Base class for every exception raised by Nexus."""


class ConfigError(NexusError):
    """Raised for configuration loading or validation problems."""


class DatabaseError(NexusError):
    """Raised for database engine, session, or backup failures."""


class MigrationError(DatabaseError):
    """Raised when applying schema migrations fails."""


class ServiceError(NexusError):
    """Base class for domain-service failures (notes, tasks, files, ...)."""


class NotFoundError(ServiceError):
    """Raised when a requested entity does not exist.

    Carries enough context to build a useful message anywhere it surfaces
    (log line, dialog, or HTTP 404 body).
    """

    def __init__(self, kind: str, identifier: object) -> None:
        super().__init__(f"{kind} {identifier!r} not found")
        self.kind = kind
        self.identifier = identifier


class ValidationError(ServiceError):
    """Raised when input fails domain validation (maps to HTTP 400)."""


class AIError(ServiceError):
    """Raised for AI-assistant failures (provider missing, request failed)."""


class AutomationError(ServiceError):
    """Raised for scheduler, watcher, or rule-execution failures."""


class PluginError(NexusError):
    """Raised when a plugin fails to load or misbehaves during a lifecycle hook."""


class ApiError(NexusError):
    """Raised for REST API server configuration or startup failures."""


class ExportError(NexusError):
    """Raised when exporting or importing workspace data fails."""
