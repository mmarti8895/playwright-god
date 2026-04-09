"""Embedding functions for the RAG pipeline.

Provides a protocol-compatible interface so that tests can inject a
fast, deterministic mock instead of a real neural-network embedder.
"""

from __future__ import annotations

import hashlib
import math
from typing import Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

EMBEDDING_DIM = 384  # matches all-MiniLM-L6-v2 used by ChromaDB default


@runtime_checkable
class EmbeddingFunction(Protocol):
    """A callable that converts a list of strings into embedding vectors."""

    def __call__(self, input: list[str]) -> list[list[float]]:  # noqa: A002
        ...


# ---------------------------------------------------------------------------
# Mock embedder (no network / no model download – deterministic)
# ---------------------------------------------------------------------------


class MockEmbedder:
    """Deterministic hash-based embedder for tests.

    Produces :data:`EMBEDDING_DIM`-dimensional unit vectors whose direction
    is determined by the MD5 hash of the input text.  Identical texts always
    produce identical vectors; near-identical texts produce nearby vectors
    because of byte-level overlap in the hash chain.
    """

    def __call__(self, input: list[str]) -> list[list[float]]:  # noqa: A002
        result: list[list[float]] = []
        for text in input:
            result.append(self._embed_one(text))
        return result

    @staticmethod
    def _embed_one(text: str) -> list[float]:
        """Return a normalised float vector of length :data:`EMBEDDING_DIM`."""
        # Build a deterministic byte stream from repeated hashing
        seed = text.encode("utf-8")
        raw: list[int] = []
        while len(raw) < EMBEDDING_DIM:
            seed = hashlib.md5(seed).digest()
            raw.extend(seed)

        # Map bytes to [-1, 1]
        vector = [(b / 127.5) - 1.0 for b in raw[:EMBEDDING_DIM]]

        # Normalise to unit length
        magnitude = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / magnitude for v in vector]


# ---------------------------------------------------------------------------
# ChromaDB default embedder (sentence-transformers all-MiniLM-L6-v2)
# ---------------------------------------------------------------------------


class DefaultEmbedder:
    """Wraps ChromaDB's built-in :class:`DefaultEmbeddingFunction`.

    Downloads the ``all-MiniLM-L6-v2`` ONNX model on first use (~30 MB).
    Requires ``chromadb`` to be installed.
    """

    def __init__(self) -> None:
        try:
            from chromadb.utils.embedding_functions import (
                DefaultEmbeddingFunction,
            )
        except ImportError as exc:
            raise ImportError(
                "chromadb is required for DefaultEmbedder. "
                "Install it with: pip install chromadb"
            ) from exc
        self._fn = DefaultEmbeddingFunction()

    def __call__(self, input: list[str]) -> list[list[float]]:  # noqa: A002
        return list(self._fn(input))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# OpenAI embedder (optional)
# ---------------------------------------------------------------------------


class OpenAIEmbedder:
    """Uses the OpenAI Embeddings API.

    Requires ``openai`` to be installed and ``OPENAI_API_KEY`` to be set.

    Parameters
    ----------
    api_key:
        OpenAI API key.  If *None*, the value of the ``OPENAI_API_KEY``
        environment variable is used.
    model:
        Embedding model name (default ``text-embedding-3-small``).
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "text-embedding-3-small",
    ) -> None:
        try:
            import openai  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "openai is required for OpenAIEmbedder. "
                "Install it with: pip install openai"
            ) from exc
        import os

        import openai

        self._client = openai.OpenAI(api_key=api_key or os.environ["OPENAI_API_KEY"])
        self.model = model

    def __call__(self, input: list[str]) -> list[list[float]]:  # noqa: A002
        response = self._client.embeddings.create(input=input, model=self.model)
        return [item.embedding for item in response.data]
