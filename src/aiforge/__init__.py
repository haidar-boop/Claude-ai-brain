"""AIForge: a modular, provider-agnostic AI coding framework.

The public API is exposed lazily (PEP 562) so ``import aiforge`` does not
eagerly import provider SDKs, parse skill manifests, or otherwise do any
heavy lifting. Only the names you actually touch get imported, and each is
imported at most once.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aiforge.__about__ import __version__
from aiforge.utils.lazy import lazy_dir, lazy_getattr

if TYPE_CHECKING:
    from aiforge.api.client import AIForge
    from aiforge.config.schema import AIForgeConfig
    from aiforge.core.engine import Engine
    from aiforge.providers.types import ChatRequest, ChatResponse, Message, Role, Usage
    from aiforge.skills.manifest import SkillManifest

__all__ = [
    "AIForge",
    "AIForgeConfig",
    "ChatRequest",
    "ChatResponse",
    "Engine",
    "Message",
    "Role",
    "SkillManifest",
    "Usage",
    "__version__",
]

_LAZY_ATTRS: dict[str, tuple[str, str]] = {
    "AIForge": ("aiforge.api.client", "AIForge"),
    "AIForgeConfig": ("aiforge.config.schema", "AIForgeConfig"),
    "Engine": ("aiforge.core.engine", "Engine"),
    "ChatRequest": ("aiforge.providers.types", "ChatRequest"),
    "ChatResponse": ("aiforge.providers.types", "ChatResponse"),
    "Message": ("aiforge.providers.types", "Message"),
    "Role": ("aiforge.providers.types", "Role"),
    "Usage": ("aiforge.providers.types", "Usage"),
    "SkillManifest": ("aiforge.skills.manifest", "SkillManifest"),
}

__getattr__ = lazy_getattr(__name__, _LAZY_ATTRS)
__dir__ = lazy_dir([*__all__])
