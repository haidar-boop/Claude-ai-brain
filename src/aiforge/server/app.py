"""A minimal, dependency-free HTTP JSON API over the engine.

Deliberately small: one POST endpoint that runs a prompt through the engine
and returns the response as JSON, plus a health check. No authentication,
no TLS, no rate limiting -- this exists so ``aiforge serve`` works out of
the box with zero extra dependencies for local development. Front it with a
real ASGI/WSGI server and framework for anything beyond that.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from aiforge.api.client import AIForge
from aiforge.utils.logging import get_logger

__all__ = ["serve"]

_logger = get_logger(__name__)
_MAX_BODY_BYTES = 10 * 1024 * 1024  # 10 MB


def serve(*, host: str = "127.0.0.1", port: int = 8420, forge: AIForge | None = None) -> None:
    """Run the HTTP JSON API, blocking until interrupted (Ctrl+C)."""
    app = forge if forge is not None else AIForge()
    handler = _make_handler(app)
    server = ThreadingHTTPServer((host, port), handler)
    _logger.info("server started", extra={"extra_fields": {"host": host, "port": port}})
    print(f"AIForge server listening on http://{host}:{port}  (POST /run, GET /health)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def _make_handler(forge: AIForge) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format_str: str, *args: Any) -> None:
            _logger.debug(format_str, extra={"extra_fields": {"args": args}})

        def do_GET(self) -> None:
            if self.path == "/health":
                self._json_response(200, {"status": "ok"})
            else:
                self._json_response(404, {"error": "not found"})

        def do_POST(self) -> None:
            if self.path != "/run":
                self._json_response(404, {"error": "not found"})
                return
            try:
                payload = self._read_json_body()
                prompt = payload.get("prompt")
                if not isinstance(prompt, str) or not prompt:
                    raise ValueError("'prompt' must be a non-empty string")
                result = forge.run_detailed(
                    prompt,
                    provider=payload.get("provider"),
                    model=payload.get("model"),
                    skills=tuple(payload.get("skills", ())),
                    system=payload.get("system"),
                    max_tokens=payload.get("max_tokens"),
                )
            except (KeyError, ValueError, TypeError) as exc:
                self._json_response(400, {"error": str(exc)})
                return
            except Exception as exc:
                self._json_response(502, {"error": str(exc)})
                return
            response = result.response
            self._json_response(
                200,
                {
                    "text": response.text,
                    "provider": result.context.provider_name,
                    "model": response.model,
                    "stop_reason": response.stop_reason,
                    "cost_usd": response.cost_usd,
                    "usage": {
                        "input_tokens": response.usage.input_tokens,
                        "output_tokens": response.usage.output_tokens,
                        "total_tokens": response.usage.total_tokens,
                    },
                },
            )

        def _read_json_body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", 0))
            if length <= 0:
                raise ValueError("empty request body")
            if length > _MAX_BODY_BYTES:
                raise ValueError("request body too large")
            raw = self.rfile.read(length)
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("request body must be a JSON object")
            return data

        def _json_response(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler
