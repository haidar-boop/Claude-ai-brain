"""Tests for nexus.services.notes."""

from __future__ import annotations

import pytest

from nexus.core.errors import NotFoundError, ValidationError
from nexus.core.events import EventBus
from nexus.db.database import Database
from nexus.services.notes import NotesService, extract_wiki_links


@pytest.fixture
def service() -> NotesService:
    return NotesService(Database.in_memory(), EventBus())


def test_extract_wiki_links_basic() -> None:
    assert extract_wiki_links("see [[Alpha]] and [[Beta]]") == ["Alpha", "Beta"]


def test_extract_wiki_links_with_display_text_and_dedup() -> None:
    body = "[[Project Ideas|ideas]] then [[ Project Ideas ]] again and [[Other]]"
    assert extract_wiki_links(body) == ["Project Ideas", "Other"]


def test_extract_wiki_links_none() -> None:
    assert extract_wiki_links("plain text, no links") == []


def test_create_and_get(service: NotesService) -> None:
    created = service.create("My Note", "hello **world**", tags=["Idea", "idea", "  "])
    fetched = service.get(created.id)
    assert fetched.title == "My Note"
    assert fetched.body == "hello **world**"
    assert fetched.tags == ("idea",)  # normalized + de-duplicated


def test_create_blank_title_rejected(service: NotesService) -> None:
    with pytest.raises(ValidationError, match="title must not be empty"):
        service.create("   ")


def test_update_records_version_on_content_change(service: NotesService) -> None:
    note = service.create("Title", "v1 body")
    service.update(note.id, body="v2 body")
    service.update(note.id, body="v3 body")
    history = service.history(note.id)
    assert [v.body for v in history] == ["v2 body", "v1 body"]  # newest first
    assert service.get(note.id).body == "v3 body"


def test_update_tags_only_does_not_create_version(service: NotesService) -> None:
    note = service.create("Title", "body")
    service.update(note.id, tags=["work"])
    assert service.history(note.id) == []
    assert service.get(note.id).tags == ("work",)


def test_update_missing_raises(service: NotesService) -> None:
    with pytest.raises(NotFoundError):
        service.update(999, body="x")


def test_delete(service: NotesService) -> None:
    note = service.create("Doomed", "x")
    service.delete(note.id)
    with pytest.raises(NotFoundError):
        service.get(note.id)


def test_list_and_filter_by_tag(service: NotesService) -> None:
    service.create("A", "x", tags=["work"])
    service.create("B", "y", tags=["home"])
    service.create("C", "z", tags=["work"])
    titles = {n.title for n in service.list_notes(tag="work")}
    assert titles == {"A", "C"}


def test_search(service: NotesService) -> None:
    service.create("Grocery list", "milk and eggs")
    service.create("Meeting notes", "discuss the milk budget")
    service.create("Unrelated", "nothing here")
    hits = {n.title for n in service.search("milk")}
    assert hits == {"Grocery list", "Meeting notes"}


def test_wiki_links_resolve_to_ids(service: NotesService) -> None:
    target = service.create("Target Note", "I am linked")
    source = service.create("Source", "please see [[Target Note]] for details")
    dto = service.get(source.id)
    assert dto.links == ("Target Note",)
    assert dto.resolved_link_ids == {"Target Note": target.id}


def test_backlinks(service: NotesService) -> None:
    target = service.create("Hub", "central note")
    service.create("Spoke 1", "links to [[Hub]]")
    service.create("Spoke 2", "also links to [[Hub]] here")
    service.create("Unrelated", "no link")
    back = {n.title for n in service.backlinks(target.id)}
    assert back == {"Spoke 1", "Spoke 2"}


def test_restore_version(service: NotesService) -> None:
    note = service.create("Doc", "original")
    service.update(note.id, body="edited")
    history = service.history(note.id)
    assert len(history) == 1
    restored = service.restore_version(note.id, history[0].id)
    assert restored.body == "original"
    # Restoring snapshotted the "edited" state, so it's recoverable too.
    assert any(v.body == "edited" for v in service.history(note.id))


def test_events_published() -> None:
    bus = EventBus()
    seen: list[str] = []
    bus.subscribe("*", lambda e: seen.append(e.name))
    svc = NotesService(Database.in_memory(), bus)
    note = svc.create("X", "y")
    svc.update(note.id, body="z")
    svc.delete(note.id)
    assert seen == ["note.created", "note.updated", "note.deleted"]
