"""Tests for the local REST API: auth, routes, and error mapping.

Uses aiohttp's in-process test client so no real socket/port is bound. The
suite runs under ``asyncio_mode = auto`` (see pyproject), so ``async def``
tests and fixtures are collected without an explicit marker.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from aiohttp.test_utils import TestClient, TestServer

from nexus.api import create_app, generate_token
from nexus.app_context import AppContext

TOKEN = "test-token-abc123"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def context() -> Any:
    ctx = AppContext.in_memory()
    try:
        yield ctx
    finally:
        ctx.close()


@pytest.fixture
async def client(context: Any) -> AsyncIterator[TestClient]:
    app = create_app(context, token=TOKEN)
    async with TestClient(TestServer(app)) as test_client:
        yield test_client


def test_create_app_requires_token(context: Any) -> None:
    with pytest.raises(ValueError, match="token is required"):
        create_app(context, token="")


def test_generate_token_is_unguessable() -> None:
    assert generate_token() != generate_token()
    assert len(generate_token()) >= 32


async def test_health_needs_no_auth(client: TestClient) -> None:
    resp = await client.get("/health")
    assert resp.status == 200
    assert (await resp.json())["status"] == "ok"


async def test_unauthorized_without_token(client: TestClient) -> None:
    resp = await client.get("/api/notes")
    assert resp.status == 401


async def test_notes_create_and_list(client: TestClient) -> None:
    resp = await client.post("/api/notes", json={"title": "API note", "tags": ["x"]}, headers=AUTH)
    assert resp.status == 201
    created = await resp.json()
    assert created["title"] == "API note"

    resp = await client.get("/api/notes", headers=AUTH)
    assert resp.status == 200
    notes = await resp.json()
    assert [n["title"] for n in notes] == ["API note"]

    note_id = created["id"]
    resp = await client.get(f"/api/notes/{note_id}", headers=AUTH)
    assert resp.status == 200
    assert (await resp.json())["id"] == note_id


async def test_missing_field_is_400(client: TestClient) -> None:
    resp = await client.post("/api/notes", json={"body": "no title"}, headers=AUTH)
    assert resp.status == 400
    assert "title" in (await resp.json())["error"]


async def test_unknown_note_is_404(client: TestClient) -> None:
    resp = await client.get("/api/notes/999", headers=AUTH)
    assert resp.status == 404


async def test_projects_tasks_and_board(client: TestClient) -> None:
    resp = await client.post("/api/projects", json={"name": "P"}, headers=AUTH)
    assert resp.status == 201
    project_id = (await resp.json())["id"]

    resp = await client.post(
        "/api/tasks", json={"project_id": project_id, "title": "T1"}, headers=AUTH
    )
    assert resp.status == 201

    resp = await client.get(f"/api/projects/{project_id}/board", headers=AUTH)
    assert resp.status == 200
    board = await resp.json()
    assert board["todo"][0]["title"] == "T1"


async def test_stats_and_search(client: TestClient, context: Any) -> None:
    context.notes.create("searchable apple note")
    resp = await client.get("/api/dashboard/stats", headers=AUTH)
    assert resp.status == 200
    assert (await resp.json())["notes"] == 1

    resp = await client.get("/api/search", params={"q": "apple"}, headers=AUTH)
    assert resp.status == 200
    results = await resp.json()
    assert any("apple" in r["title"].lower() or "apple" in r["snippet"].lower() for r in results)


async def test_bad_json_is_400(client: TestClient) -> None:
    resp = await client.post(
        "/api/notes", data="not json", headers={**AUTH, "Content-Type": "application/json"}
    )
    assert resp.status == 400
