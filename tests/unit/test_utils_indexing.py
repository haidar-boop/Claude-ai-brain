"""Tests for aiforge.utils.indexing."""

from __future__ import annotations

from aiforge.utils.indexing import InvertedIndex


def test_add_and_query_single_token() -> None:
    index = InvertedIndex()
    index.add("python", ["python", "py", "pep8"])
    assert index.query(["python"]) == {"python"}


def test_query_is_case_insensitive() -> None:
    index = InvertedIndex()
    index.add("python", ["Python"])
    assert index.query(["PYTHON"]) == {"python"}


def test_query_union_across_tokens() -> None:
    index = InvertedIndex()
    index.add("python", ["scripting"])
    index.add("bash", ["scripting", "shell"])
    assert index.query(["scripting"]) == {"python", "bash"}
    assert index.query(["shell"]) == {"bash"}


def test_query_all_intersection() -> None:
    index = InvertedIndex()
    index.add("react", ["javascript", "frontend"])
    index.add("django", ["python", "backend"])
    index.add("fastapi", ["python", "backend", "async"])
    assert index.query_all(["python", "backend"]) == {"django", "fastapi"}
    assert index.query_all(["python", "async"]) == {"fastapi"}


def test_query_all_empty_tokens_returns_empty_set() -> None:
    index = InvertedIndex()
    index.add("python", ["python"])
    assert index.query_all([]) == set()


def test_remove_clears_item_and_empty_buckets() -> None:
    index = InvertedIndex()
    index.add("python", ["scripting"])
    assert "python" in index
    index.remove("python")
    assert "python" not in index
    assert index.query(["scripting"]) == set()


def test_remove_missing_item_is_noop() -> None:
    index = InvertedIndex()
    index.remove("nonexistent")
    assert len(index) == 0


def test_re_adding_item_replaces_previous_tokens() -> None:
    index = InvertedIndex()
    index.add("python", ["old_token"])
    index.add("python", ["new_token"])
    assert index.query(["old_token"]) == set()
    assert index.query(["new_token"]) == {"python"}


def test_len_and_contains() -> None:
    index = InvertedIndex()
    index.add("a", ["x"])
    index.add("b", ["y"])
    assert len(index) == 2
    assert "a" in index
    assert "z" not in index
