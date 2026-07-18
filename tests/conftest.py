"""Shared pytest fixtures and configuration for the AIForge test suite.

Fixtures are added incrementally as the corresponding subsystems are built;
subsystem-specific fixtures that don't need to be shared live in the
individual ``test_*`` modules instead.
"""

from __future__ import annotations
