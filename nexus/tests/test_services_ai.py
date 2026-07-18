"""Tests for nexus.services.ai (runs against AIForge's zero-cost fake provider)."""

from __future__ import annotations

import pytest

from nexus.core.config import AIConfig
from nexus.core.errors import NotFoundError, ValidationError
from nexus.core.events import EventBus
from nexus.db.database import Database
from nexus.services.ai import AIService


@pytest.fixture
def service() -> AIService:
    # default_provider "fake" -> no network, no key, deterministic.
    return AIService(Database.in_memory(), AIConfig(default_provider="fake"), EventBus())


def test_summarize_returns_text(service: AIService) -> None:
    out = service.summarize("A long document about quarterly results and growth.")
    assert isinstance(out, str)
    assert out  # the fake provider echoes a deterministic response


def test_explain_code(service: AIService) -> None:
    out = service.explain_code("def add(a, b):\n    return a + b")
    assert isinstance(out, str) and out


def test_rewrite_and_email(service: AIService) -> None:
    assert service.rewrite("make this formal", style="formal")
    assert service.generate_email("decline a meeting politely")


def test_create_and_get_session(service: AIService) -> None:
    created = service.create_session("Planning")
    fetched = service.get_session(created.id)
    assert fetched.title == "Planning"
    assert fetched.provider == "fake"
    assert fetched.messages == ()


def test_send_message_persists_both_turns(service: AIService) -> None:
    chat = service.create_session()
    reply = service.send_message(chat.id, "Hello there")
    assert reply.role == "assistant"
    history = service.get_session(chat.id).messages
    assert [m.role for m in history] == ["user", "assistant"]
    assert history[0].content == "Hello there"


def test_send_empty_message_rejected(service: AIService) -> None:
    chat = service.create_session()
    with pytest.raises(ValidationError):
        service.send_message(chat.id, "   ")


def test_send_to_missing_session(service: AIService) -> None:
    with pytest.raises(NotFoundError):
        service.send_message(999, "hi")


def test_history_is_bounded(service: AIService) -> None:
    svc = AIService(
        Database.in_memory(),
        AIConfig(default_provider="fake", max_history_messages=4),
        EventBus(),
    )
    chat = svc.create_session()
    for i in range(6):
        svc.send_message(chat.id, f"message {i}")
    # All turns are persisted even though only the last few are sent as context.
    assert len(svc.get_session(chat.id).messages) == 12  # 6 user + 6 assistant


def test_delete_session(service: AIService) -> None:
    chat = service.create_session()
    service.delete_session(chat.id)
    with pytest.raises(NotFoundError):
        service.get_session(chat.id)


def test_semantic_file_search(service: AIService) -> None:
    service.index_file_text(1, "python programming and software engineering", snippet="a")
    service.index_file_text(2, "gardening tips for tomatoes", snippet="b")
    service.index_file_text(3, "advanced software engineering practices", snippet="c")
    matches = service.semantic_search("software engineering", limit=2)
    ids = {m.file_id for m in matches}
    assert 1 in ids or 3 in ids
    assert 2 not in ids or matches[-1].file_id == 2


def test_remove_file_index(service: AIService) -> None:
    service.index_file_text(1, "findable embedded content")
    service.remove_file_index(1)
    assert service.semantic_search("findable") == []


def test_events_published(service: AIService) -> None:
    seen: list[str] = []
    service._events.subscribe("*", lambda e: seen.append(e.name))
    chat = service.create_session()
    service.send_message(chat.id, "hi")
    service.delete_session(chat.id)
    assert "chat.session_created" in seen
    assert "chat.message_sent" in seen
    assert "chat.session_deleted" in seen
