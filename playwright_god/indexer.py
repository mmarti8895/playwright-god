"""RAG indexer: stores and retrieves repository chunks via ChromaDB.

Uses ChromaDB as the vector store.  For tests, an in-memory
:class:`chromadb.EphemeralClient` is used; for production, a
:class:`chromadb.PersistentClient` persists the index to disk.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .chunker import Chunk
from .embedder import DefaultEmbedder, EmbeddingFunction


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class SearchResult:
    """A single search hit returned by :meth:`RepositoryIndexer.search`."""

    chunk: Chunk
    distance: float   # lower is better (cosine / L2)
    score: float      # 1 - distance (higher is better, range [0, 1])

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"SearchResult(file={self.chunk.file_path!r}, "
            f"lines={self.chunk.start_line}-{self.chunk.end_line}, "
            f"score={self.score:.3f})"
        )


# ---------------------------------------------------------------------------
# Indexer
# ---------------------------------------------------------------------------

_METADATA_KEYS = ("file_path", "start_line", "end_line", "language")


class RepositoryIndexer:
    """ChromaDB-backed vector store for repository chunks.

    Parameters
    ----------
    collection_name:
        Name of the ChromaDB collection.
    persist_dir:
        If given, chunks are persisted to this directory between runs
        (:class:`chromadb.PersistentClient`).  If *None*, an in-memory
        :class:`chromadb.EphemeralClient` is used.
    embedder:
        An :class:`~playwright_god.embedder.EmbeddingFunction` instance.
        Defaults to :class:`~playwright_god.embedder.DefaultEmbedder`.
    """

    def __init__(
        self,
        collection_name: str = "repo",
        persist_dir: str | None = None,
        embedder: EmbeddingFunction | None = None,
    ) -> None:
        try:
            import chromadb
        except ImportError as exc:
            raise ImportError(
                "chromadb is required. Install it with: pip install chromadb"
            ) from exc

        self._embedder: EmbeddingFunction = embedder or DefaultEmbedder()

        if persist_dir is not None:
            self._client = chromadb.PersistentClient(path=persist_dir)
        else:
            self._client = chromadb.EphemeralClient()

        # We manage embeddings ourselves so we pass them explicitly; this
        # allows us to swap in any EmbeddingFunction (including mocks).
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_chunks(self, chunks: Sequence[Chunk]) -> None:
        """Embed and store *chunks* in the collection.

        Chunks whose :attr:`~Chunk.chunk_id` already exists are silently
        skipped (idempotent).
        """
        if not chunks:
            return

        # Compute embeddings in one batch call
        texts = [c.content for c in chunks]
        embeddings = self._embedder(texts)

        ids: list[str] = []
        metadatas: list[dict] = []
        documents: list[str] = []
        vecs: list[list[float]] = []

        for chunk, emb in zip(chunks, embeddings):
            ids.append(chunk.chunk_id)
            metadatas.append(
                {
                    "file_path": chunk.file_path,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "language": chunk.language,
                }
            )
            documents.append(chunk.content)
            vecs.append(emb)

        # ChromaDB upsert handles duplicates gracefully
        self._collection.upsert(
            ids=ids,
            embeddings=vecs,
            metadatas=metadatas,
            documents=documents,
        )

    def search(self, query: str, n_results: int = 5) -> list[SearchResult]:
        """Return the top-*n_results* chunks most similar to *query*.

        Results are ordered by descending relevance score (ascending distance).
        """
        n_results = min(n_results, max(self.count(), 1))
        query_embedding = self._embedder([query])[0]

        raw = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )

        results: list[SearchResult] = []
        documents = (raw.get("documents") or [[]])[0]
        metadatas = (raw.get("metadatas") or [[]])[0]
        distances = (raw.get("distances") or [[]])[0]
        ids = (raw.get("ids") or [[]])[0]

        for doc, meta, dist, chunk_id in zip(documents, metadatas, distances, ids):
            chunk = Chunk(
                file_path=meta.get("file_path", ""),
                content=doc,
                start_line=int(meta.get("start_line", 0)),
                end_line=int(meta.get("end_line", 0)),
                language=meta.get("language", "unknown"),
                chunk_id=chunk_id,
            )
            score = max(0.0, 1.0 - float(dist))
            results.append(SearchResult(chunk=chunk, distance=float(dist), score=score))

        return results

    def count(self) -> int:
        """Return the number of chunks stored in the collection."""
        return self._collection.count()

    def get_chunk_stubs(self) -> list[Chunk]:
        """Return lightweight :class:`Chunk` objects for every stored chunk.

        Each returned chunk has an empty :attr:`~Chunk.content` string; only
        the id and metadata fields (``file_path``, ``start_line``,
        ``end_line``, ``language``) are populated.  This is efficient for
        operations that only need the file/line inventory (e.g. building a
        memory map) because it avoids fetching the full document text.
        """
        raw = self._collection.get(include=["metadatas"])
        return [
            Chunk(
                file_path=meta.get("file_path", ""),
                content="",
                start_line=int(meta.get("start_line", 0)),
                end_line=int(meta.get("end_line", 0)),
                language=meta.get("language", "unknown"),
                chunk_id=chunk_id,
            )
            for chunk_id, meta in zip(
                raw.get("ids") or [],
                raw.get("metadatas") or [],
            )
        ]

    def clear(self) -> None:
        """Remove all chunks from the collection."""
        self._client.delete_collection(self._collection.name)
        self._collection = self._client.get_or_create_collection(
            name=self._collection.name,
            metadata={"hnsw:space": "cosine"},
        )
