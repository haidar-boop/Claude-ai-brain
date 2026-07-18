"""A small local REST API over the workspace services.

The API is off by default and binds to localhost with a bearer token, so it
is a convenience for local scripting and integrations rather than a public
service. It reuses the exact same :class:`~nexus.app_context.AppContext`
services the GUI and CLI use, so there is one implementation of the business
logic and three front ends over it.
"""

from __future__ import annotations

from nexus.api.server import create_app, generate_token, run_server

__all__ = ["create_app", "generate_token", "run_server"]
