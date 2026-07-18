"""Nexus: a personal productivity and AI workspace.

The public surface is intentionally small -- an application is launched via
``nexus.cli`` or ``python -m nexus``; libraries embedding pieces of Nexus
import the specific service they need (``nexus.services.notes`` etc.).
Importing :mod:`nexus` itself stays cheap: nothing heavy (Qt, SQLAlchemy)
is imported until actually used.
"""

from nexus.__about__ import __version__

__all__ = ["__version__"]
