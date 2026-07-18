"""Tests for nexus.ai.embeddings."""

from __future__ import annotations

import numpy as np
import pytest

from nexus.ai.embeddings import HashingEmbedder, VectorStore
from nexus.db.database import Database


def test_embedding_is_unit_norm() -> None:
    emb = HashingEmbedder(128)
    vector = emb.embed("the quick brown fox")
    assert vector.shape == (128,)
    assert np.isclose(np.linalg.norm(vector), 1.0)


def test_empty_text_is_zero_vector() -> None:
    emb = HashingEmbedder(64)
    vector = emb.embed("!!!  ---")  # no alphanumeric tokens
    assert np.allclose(vector, 0.0)


def test_embedding_is_deterministic() -> None:
    emb = HashingEmbedder(64)
    assert np.array_equal(emb.embed("hello world"), emb.embed("hello world"))


def test_similar_text_scores_higher_than_dissimilar() -> None:
    emb = HashingEmbedder(512)
    query = emb.embed("machine learning models and neural networks")
    close = emb.embed("neural networks are machine learning models")
    far = emb.embed("banana bread recipe with walnuts")
    assert float(query @ close) > float(query @ far)


def test_dimensions_validated() -> None:
    with pytest.raises(ValueError, match="dimensions"):
        HashingEmbedder(8)


def test_vector_store_search_ranks_by_similarity() -> None:
    store = VectorStore(Database.in_memory(), HashingEmbedder(256))
    store.upsert("file", 1, "python programming tutorial for beginners", snippet="py")
    store.upsert("file", 2, "chocolate cake baking recipe", snippet="cake")
    store.upsert("file", 3, "advanced python programming techniques", snippet="py2")
    hits = store.search("python programming", limit=2)
    assert [h.source_id for h in hits] == [1, 3] or [h.source_id for h in hits] == [3, 1]
    assert all(h.source_type == "file" for h in hits)


def test_vector_store_upsert_replaces() -> None:
    store = VectorStore(Database.in_memory(), HashingEmbedder(128))
    store.upsert("file", 1, "original apple text")
    store.upsert("file", 1, "different banana text")
    hits = store.search("banana", limit=5)
    # Only one record for file 1, matching the new content.
    assert len([h for h in hits if h.source_id == 1]) == 1


def test_vector_store_remove() -> None:
    store = VectorStore(Database.in_memory(), HashingEmbedder(128))
    store.upsert("file", 1, "findable content")
    store.remove("file", 1)
    assert store.search("findable") == []


def test_search_filters_by_source_type() -> None:
    store = VectorStore(Database.in_memory(), HashingEmbedder(128))
    store.upsert("file", 1, "shared keyword content")
    store.upsert("note", 2, "shared keyword content")
    hits = store.search("shared keyword", source_type="note")
    assert [h.source_id for h in hits] == [2]


def test_search_ignores_mismatched_dimensions() -> None:
    db = Database.in_memory()
    VectorStore(db, HashingEmbedder(128)).upsert("file", 1, "some text")
    # A store with a different embedder dimension must ignore the 128-dim row.
    other = VectorStore(db, HashingEmbedder(256))
    assert other.search("some text") == []
