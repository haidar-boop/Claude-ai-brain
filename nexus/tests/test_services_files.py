"""Tests for nexus.services.files."""

from __future__ import annotations

from pathlib import Path

import pytest

from nexus.core.errors import NotFoundError, ValidationError
from nexus.core.events import EventBus
from nexus.db.database import Database
from nexus.services.files import FilesService, OrganizeRule


@pytest.fixture
def service() -> FilesService:
    return FilesService(Database.in_memory(), EventBus())


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_index_and_search_by_content(service: FilesService, tmp_path: Path) -> None:
    _write(tmp_path / "recipe.txt", "how to make sourdough bread with a starter")
    _write(tmp_path / "notes.md", "meeting agenda about quarterly budget")
    service.index_directory(tmp_path)
    hits = service.search("sourdough")
    assert [h.name for h in hits] == ["recipe.txt"]


def test_search_by_name(service: FilesService, tmp_path: Path) -> None:
    _write(tmp_path / "budget-2024.csv", "a,b,c")
    service.index_directory(tmp_path)
    hits = service.search("budget")
    assert len(hits) == 1


def test_search_empty_query(service: FilesService) -> None:
    assert service.search("   ") == []


def test_search_with_punctuation_does_not_error(service: FilesService, tmp_path: Path) -> None:
    _write(tmp_path / "report.txt", "the final report(v2) is ready")
    service.index_directory(tmp_path)
    # Punctuation would be FTS5 syntax; the service must quote it safely.
    assert service.search("report(v2)") != [] or service.search("final") != []


def test_reindex_updates_content(service: FilesService, tmp_path: Path) -> None:
    path = _write(tmp_path / "doc.txt", "original apple content")
    service.index_file(path)
    assert service.search("apple")
    _write(path, "replaced banana content")
    service.index_file(path)
    assert service.search("banana")
    assert service.search("apple") == []  # old content no longer matches


def test_index_nonexistent_file(service: FilesService, tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        service.index_file(tmp_path / "ghost.txt")


def test_remove_from_index(service: FilesService, tmp_path: Path) -> None:
    path = _write(tmp_path / "temp.txt", "findable text here")
    dto = service.index_file(path)
    service.remove(dto.id)
    assert service.search("findable") == []
    with pytest.raises(NotFoundError):
        service.remove(dto.id)


def test_find_duplicates_two_stage(service: FilesService, tmp_path: Path) -> None:
    _write(tmp_path / "a.txt", "identical content")
    _write(tmp_path / "b.txt", "identical content")  # dup of a
    _write(tmp_path / "c.txt", "unique content here")  # different
    _write(tmp_path / "d.txt", "xy")  # unique size
    service.index_directory(tmp_path)
    groups = service.find_duplicates()
    assert len(groups) == 1
    names = {f.name for f in groups[0].files}
    assert names == {"a.txt", "b.txt"}


def test_no_duplicates(service: FilesService, tmp_path: Path) -> None:
    _write(tmp_path / "a.txt", "one")
    _write(tmp_path / "b.txt", "different length content")
    service.index_directory(tmp_path)
    assert service.find_duplicates() == []


def test_preview(service: FilesService, tmp_path: Path) -> None:
    path = _write(tmp_path / "readme.md", "# Title\nsome body text")
    preview = service.preview(path)
    assert preview.name == "readme.md"
    assert preview.size_bytes > 0
    assert "Title" in preview.snippet


def test_organize_dry_run_plans_but_does_not_move(service: FilesService, tmp_path: Path) -> None:
    _write(tmp_path / "photo.jpg", "img")
    _write(tmp_path / "song.mp3", "audio")
    _write(tmp_path / "keep.txt", "text")
    rules = [
        OrganizeRule(destination="Images", extensions=("jpg", "png")),
        OrganizeRule(destination="Audio", extensions=("mp3",)),
    ]
    plan = service.organize(tmp_path, rules, dry_run=True)
    assert len(plan) == 2  # keep.txt matches nothing
    assert (tmp_path / "photo.jpg").exists()  # nothing actually moved


def test_organize_performs_moves(service: FilesService, tmp_path: Path) -> None:
    _write(tmp_path / "photo.jpg", "img")
    rules = [OrganizeRule(destination="Images", extensions=("jpg",))]
    service.organize(tmp_path, rules, dry_run=False)
    assert not (tmp_path / "photo.jpg").exists()
    assert (tmp_path / "Images" / "photo.jpg").exists()


def test_organize_by_glob(service: FilesService, tmp_path: Path) -> None:
    _write(tmp_path / "invoice-2024.pdf", "x")
    _write(tmp_path / "other.pdf", "y")
    rules = [OrganizeRule(destination="Invoices", glob="invoice-*.pdf")]
    plan = service.organize(tmp_path, rules, dry_run=True)
    assert len(plan) == 1
    assert "invoice-2024.pdf" in plan[0].source


def test_custom_text_extractor_is_used(tmp_path: Path) -> None:
    class UpperExtractor:
        def extract(self, path: Path) -> str:
            return "OCRTEXT MAGICWORD"

    svc = FilesService(Database.in_memory(), EventBus(), extractor=UpperExtractor())
    _write(tmp_path / "scan.png", "binary-ish")
    svc.index_file(tmp_path / "scan.png")
    assert svc.search("MAGICWORD")  # extractor's text was indexed


def test_events_published(tmp_path: Path) -> None:
    bus = EventBus()
    seen: list[str] = []
    bus.subscribe("*", lambda e: seen.append(e.name))
    svc = FilesService(Database.in_memory(), bus)
    path = _write(tmp_path / "f.txt", "content")
    dto = svc.index_file(path)
    svc.remove(dto.id)
    assert seen == ["file.indexed", "file.removed"]
