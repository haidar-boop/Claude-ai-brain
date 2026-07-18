"""Tests for aiforge.server.app."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from http.server import ThreadingHTTPServer

import pytest

from aiforge.api.client import AIForge
from aiforge.config.schema import AIForgeConfig, EngineConfig
from aiforge.server.app import _make_handler


@pytest.fixture
def server_url() -> Iterator[str]:
    forge = AIForge(config=AIForgeConfig(engine=EngineConfig(default_provider="fake")))
    handler = _make_handler(forge)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    try:
        yield f"http://{host}:{port}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def _post(url: str, payload: dict[str, object]) -> tuple[int, dict[str, object]]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_health_endpoint(server_url: str) -> None:
    with urllib.request.urlopen(f"{server_url}/health", timeout=5) as response:
        assert response.status == 200
        assert json.loads(response.read()) == {"status": "ok"}


def test_unknown_get_path_returns_404(server_url: str) -> None:
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(f"{server_url}/nope", timeout=5)
    assert exc_info.value.code == 404


def test_run_endpoint_returns_response(server_url: str) -> None:
    status, body = _post(f"{server_url}/run", {"prompt": "hello there", "provider": "fake"})
    assert status == 200
    assert "hello there" in body["text"]
    assert body["provider"] == "fake"
    assert "usage" in body


def test_run_endpoint_missing_prompt_returns_400(server_url: str) -> None:
    status, body = _post(f"{server_url}/run", {})
    assert status == 400
    assert "error" in body


def test_run_endpoint_unknown_provider_returns_502(server_url: str) -> None:
    status, body = _post(f"{server_url}/run", {"prompt": "hi", "provider": "does-not-exist"})
    assert status == 502
    assert "error" in body


def test_run_endpoint_wrong_method_path_returns_404(server_url: str) -> None:
    status, _ = _post(f"{server_url}/health", {"prompt": "hi"})
    assert status == 404
