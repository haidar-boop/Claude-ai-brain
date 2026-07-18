"""Test the demo data seeder."""

from __future__ import annotations

from typing import Any

from nexus.demo import seed_workspace


def test_seed_workspace_populates_every_module(app_ctx: Any) -> None:
    seed_workspace(app_ctx)

    assert len(app_ctx.notes.list_notes()) == 4
    assert len(app_ctx.tasks.list_projects()) == 2

    stats = app_ctx.dashboard.stats()
    assert stats.notes == 4
    assert stats.tasks == 6
    assert stats.completed_tasks == 1
    assert stats.chat_sessions == 1

    rules = app_ctx.automation.list_rules()
    assert len(rules) == 1
    assert rules[0].trigger == "note.created"


def test_seed_is_wiki_linked(app_ctx: Any) -> None:
    seed_workspace(app_ctx)
    welcome = next(n for n in app_ctx.notes.list_notes() if n.title == "Welcome to Nexus")
    assert "Project Ideas" in welcome.links
