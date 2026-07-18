"""The aiohttp application: routes, auth, and JSON encoding.

Every route delegates to a service on the :class:`AppContext`; the handlers
only parse input, call the service, and encode DTOs to JSON. Service calls
are synchronous SQLite operations run directly on the event-loop thread --
which is intentional: the on-disk database enforces same-thread access, and
these calls are sub-millisecond, so offloading them to a worker thread would
break SQLite's threading rule for no real latency win on a local API.

Auth is a single bearer-token check applied by middleware to everything
except ``/health``; the token is compared in constant time.
"""

from __future__ import annotations

import datetime as dt
import json
import secrets
from dataclasses import asdict, is_dataclass
from typing import Any

from aiohttp import web

from nexus.app_context import AppContext
from nexus.core.errors import NexusError, NotFoundError, ValidationError
from nexus.core.logging import get_logger

__all__ = ["create_app", "generate_token", "run_server"]

_logger = get_logger("api")


def generate_token() -> str:
    """Return a fresh URL-safe API token."""
    return secrets.token_urlsafe(32)


def _default(value: Any) -> Any:
    if isinstance(value, dt.datetime):
        return value.isoformat()
    raise TypeError(f"cannot serialise {type(value).__name__}")


def _encode(obj: Any) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    if isinstance(obj, list | tuple):
        return [_encode(item) for item in obj]
    if isinstance(obj, dict):
        return {key: _encode(value) for key, value in obj.items()}
    return obj


def _json(data: Any, *, status: int = 200) -> web.Response:
    return web.json_response(
        _encode(data), status=status, dumps=lambda o: json.dumps(o, default=_default)
    )


def create_app(context: AppContext, *, token: str) -> web.Application:
    """Build the aiohttp application with auth and every route wired."""
    if not token:
        raise ValueError("an API token is required; refusing to start without one")

    @web.middleware
    async def auth_middleware(request: web.Request, handler: Any) -> web.StreamResponse:
        if request.path == "/health":
            return await handler(request)  # type: ignore[no-any-return]
        provided = request.headers.get("Authorization", "")
        if not secrets.compare_digest(provided, f"Bearer {token}"):
            return _json({"error": "unauthorized"}, status=401)
        return await handler(request)  # type: ignore[no-any-return]

    @web.middleware
    async def error_middleware(request: web.Request, handler: Any) -> web.StreamResponse:
        try:
            return await handler(request)  # type: ignore[no-any-return]
        except NotFoundError as exc:
            return _json({"error": str(exc)}, status=404)
        except ValidationError as exc:
            return _json({"error": str(exc)}, status=400)
        except NexusError as exc:
            _logger.warning("service error handling %s: %s", request.path, exc)
            return _json({"error": str(exc)}, status=400)

    app = web.Application(middlewares=[error_middleware, auth_middleware])

    async def health(_request: web.Request) -> web.Response:
        return _json({"status": "ok", "app": "nexus"})

    async def list_notes(_request: web.Request) -> web.Response:
        return _json(context.notes.list_notes())

    async def create_note(request: web.Request) -> web.Response:
        body = await _read_json(request)
        note = context.notes.create(
            _require(body, "title"),
            body.get("body", ""),
            tags=list(body.get("tags", [])),
        )
        return _json(note, status=201)

    async def get_note(request: web.Request) -> web.Response:
        note = context.notes.get(_int_param(request, "note_id"))
        return _json(note)

    async def list_projects(_request: web.Request) -> web.Response:
        return _json(context.tasks.list_projects())

    async def create_project(request: web.Request) -> web.Response:
        body = await _read_json(request)
        project = context.tasks.create_project(_require(body, "name"), body.get("description", ""))
        return _json(project, status=201)

    async def board(request: web.Request) -> web.Response:
        project_id = _int_param(request, "project_id")
        return _json(context.tasks.board(project_id))

    async def create_task(request: web.Request) -> web.Response:
        body = await _read_json(request)
        task = context.tasks.add_task(
            int(_require(body, "project_id")),
            _require(body, "title"),
            description=body.get("description", ""),
            status=body.get("status", "todo"),
        )
        return _json(task, status=201)

    async def stats(_request: web.Request) -> web.Response:
        return _json(context.dashboard.stats())

    async def search(request: web.Request) -> web.Response:
        query = request.query.get("q", "").strip()
        return _json(context.dashboard.search(query) if query else [])

    app.add_routes(
        [
            web.get("/health", health),
            web.get("/api/notes", list_notes),
            web.post("/api/notes", create_note),
            web.get("/api/notes/{note_id}", get_note),
            web.get("/api/projects", list_projects),
            web.post("/api/projects", create_project),
            web.get("/api/projects/{project_id}/board", board),
            web.post("/api/tasks", create_task),
            web.get("/api/dashboard/stats", stats),
            web.get("/api/search", search),
        ]
    )
    return app


async def _read_json(request: web.Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except json.JSONDecodeError as exc:
        raise ValidationError("request body must be valid JSON") from exc
    if not isinstance(data, dict):
        raise ValidationError("request body must be a JSON object")
    return data


def _require(body: dict[str, Any], key: str) -> Any:
    if key not in body:
        raise ValidationError(f"missing required field {key!r}")
    return body[key]


def _int_param(request: web.Request, name: str) -> int:
    try:
        return int(request.match_info[name])
    except (KeyError, ValueError) as exc:
        raise ValidationError(f"invalid {name}") from exc


def run_server(context: AppContext, *, host: str, port: int, token: str) -> None:
    """Run the API server until interrupted (blocking)."""
    app = create_app(context, token=token)
    _logger.info("starting API on http://%s:%d", host, port)
    web.run_app(app, host=host, port=port, print=None)
