"""AI support: embeddings and a local vector store for semantic search.

Kept separate from :mod:`nexus.services.ai` (which orchestrates chat and
document actions) so the embedding strategy and the vector store can be
swapped or tested on their own. The default embedder is deterministic and
dependency-free, so semantic file search works offline with no model
download and no API cost; a real embedding model can be dropped in behind
the :class:`~nexus.ai.embeddings.Embedder` protocol.
"""
