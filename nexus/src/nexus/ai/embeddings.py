"""Embeddings and a local, SQLite-backed vector store for semantic search.

The :class:`Embedder` protocol turns text into a fixed-length unit vector.
The default :class:`HashingEmbedder` uses the hashing trick (feature hashing
over tokens) so it is deterministic, fast, offline, and free -- good enough
to make "find files about X" work out of the box. It is deliberately simple
and swappable: give the service any object satisfying :class:`Embedder`
(e.g. one that calls a real sentence-embedding model or an embeddings API)
and semantic search transparently gets better, with no other code changes.

The :class:`VectorStore` persists vectors as compact float32 bytes in the
``vector_records`` table and ranks candidates by cosine similarity. Because
every vector the embedders here produce is L2-normalized, cosine similarity
is just a dot product, which numpy computes over the whole candidate set at
once.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Protocol

import numpy as np
from sqlalchemy import delete, select

from nexus.core.logging import get_logger
from nexus.db.database import Database
from nexus.db.models import VectorRecord

__all__ = [
    "Embedder",
    "HashingEmbedder",
    "SearchHit",
    "VectorStore",
]

_logger = get_logger("ai.embeddings")
_TOKEN_RE = re.compile(r"[a-z0-9]+")


class Embedder(Protocol):
    """Turns text into a fixed-length, L2-normalized float vector."""

    @property
    def dimensions(self) -> int:
        """The length of every vector this embedder produces."""
        ...

    def embed(self, text: str) -> np.ndarray:
        """Return the embedding of *text* as a 1-D float32 array."""
        ...


class HashingEmbedder:
    """A deterministic, dependency-free embedder using the hashing trick.

    Each token is hashed to a bucket in ``[0, dimensions)`` and a sign, and
    contributes to that bucket. The resulting vector is L2-normalized so
    cosine similarity reduces to a dot product. Texts that share many tokens
    land near each other, which is enough for keyword-flavoured semantic
    search without any model or network call.
    """

    def __init__(self, dimensions: int = 256) -> None:
        if dimensions < 16:
            raise ValueError("dimensions must be >= 16")
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(self, text: str) -> np.ndarray:
        vector = np.zeros(self._dimensions, dtype=np.float32)
        for token in _TOKEN_RE.findall(text.lower()):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "little") % self._dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[bucket] += sign
        norm = float(np.linalg.norm(vector))
        if norm > 0.0:
            vector /= norm
        return vector


@dataclass(frozen=True, slots=True)
class SearchHit:
    """A vector-store match: what was found and how similar it is."""

    source_type: str
    source_id: int
    score: float
    snippet: str


class VectorStore:
    """Persists embeddings and ranks them by cosine similarity."""

    def __init__(self, database: Database, embedder: Embedder) -> None:
        self._db = database
        self._embedder = embedder

    def upsert(self, source_type: str, source_id: int, text: str, *, snippet: str = "") -> None:
        """Embed *text* and store it for *(source_type, source_id)*.

        Any existing vector for the same source is replaced, so re-indexing
        updated content never leaves a stale duplicate behind.
        """
        vector = self._embedder.embed(text)
        blob = vector.astype(np.float32).tobytes()
        with self._db.session() as session:
            session.execute(
                delete(VectorRecord).where(
                    VectorRecord.source_type == source_type,
                    VectorRecord.source_id == source_id,
                )
            )
            session.add(
                VectorRecord(
                    source_type=source_type,
                    source_id=source_id,
                    dimensions=self._embedder.dimensions,
                    vector=blob,
                    snippet=snippet[:500],
                )
            )

    def remove(self, source_type: str, source_id: int) -> None:
        """Delete the stored vector for a source, if any."""
        with self._db.session() as session:
            session.execute(
                delete(VectorRecord).where(
                    VectorRecord.source_type == source_type,
                    VectorRecord.source_id == source_id,
                )
            )

    def search(
        self, query: str, *, source_type: str | None = None, limit: int = 10
    ) -> list[SearchHit]:
        """Return the most similar stored vectors to *query*, best first.

        Vectors whose dimension count doesn't match the query embedding are
        skipped (they were produced by a different embedder), so switching
        embedders can never crash search on a mixed store -- it just ignores
        the incompatible leftovers until they're re-indexed.
        """
        query_vector = self._embedder.embed(query)
        with self._db.session() as session:
            stmt = select(VectorRecord)
            if source_type is not None:
                stmt = stmt.where(VectorRecord.source_type == source_type)
            records = session.scalars(stmt).all()
            rows = [
                (r.source_type, r.source_id, r.vector, r.snippet)
                for r in records
                if r.dimensions == self._embedder.dimensions
            ]
        if not rows:
            return []
        matrix = np.stack([np.frombuffer(blob, dtype=np.float32) for _, _, blob, _ in rows])
        scores = matrix @ query_vector  # cosine, since all vectors are unit-norm
        order = np.argsort(-scores)[:limit]
        return [
            SearchHit(
                source_type=rows[i][0],
                source_id=rows[i][1],
                score=float(scores[i]),
                snippet=rows[i][3],
            )
            for i in order
            if scores[i] > 0.0
        ]
