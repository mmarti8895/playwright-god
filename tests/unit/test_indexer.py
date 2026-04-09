"""Unit tests for playwright_god.indexer."""

from __future__ import annotations

import pytest

from playwright_god.chunker import Chunk
from playwright_god.embedder import MockEmbedder
from playwright_god.indexer import RepositoryIndexer, SearchResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_chunk(
    file_path: str = "src/app.py",
    content: str = "hello world",
    start_line: int = 1,
    end_line: int = 5,
    language: str = "python",
    chunk_id: str | None = None,
) -> Chunk:
    return Chunk(
        file_path=file_path,
        content=content,
        start_line=start_line,
        end_line=end_line,
        language=language,
        chunk_id=chunk_id or Chunk._make_id(file_path, start_line, end_line),
    )


# ---------------------------------------------------------------------------
# RepositoryIndexer
# ---------------------------------------------------------------------------


class TestRepositoryIndexerInit:
    def test_creates_in_memory_indexer(self, in_memory_indexer):
        assert in_memory_indexer.count() == 0

    def test_custom_collection_name(self):
        indexer = RepositoryIndexer(
            collection_name="custom",
            persist_dir=None,
            embedder=MockEmbedder(),
        )
        assert indexer.count() == 0


class TestAddChunks:
    def test_add_single_chunk(self, in_memory_indexer):
        chunk = make_chunk(chunk_id="id001")
        in_memory_indexer.add_chunks([chunk])
        assert in_memory_indexer.count() == 1

    def test_add_multiple_chunks(self, in_memory_indexer):
        chunks = [make_chunk(file_path=f"file{i}.py", chunk_id=f"id{i:03d}") for i in range(5)]
        in_memory_indexer.add_chunks(chunks)
        assert in_memory_indexer.count() == 5

    def test_add_empty_list_is_noop(self, in_memory_indexer):
        in_memory_indexer.add_chunks([])
        assert in_memory_indexer.count() == 0

    def test_upsert_idempotent(self, in_memory_indexer):
        chunk = make_chunk(chunk_id="dup001")
        in_memory_indexer.add_chunks([chunk])
        in_memory_indexer.add_chunks([chunk])  # duplicate
        assert in_memory_indexer.count() == 1


class TestSearch:
    def test_search_returns_results(self, in_memory_indexer):
        chunks = [
            make_chunk(
                file_path="login.py",
                content="def login(user, password): ...",
                chunk_id="c001",
            ),
            make_chunk(
                file_path="todo.py",
                content="def add_todo(title): ...",
                chunk_id="c002",
            ),
        ]
        in_memory_indexer.add_chunks(chunks)
        results = in_memory_indexer.search("login function")
        assert len(results) > 0
        assert all(isinstance(r, SearchResult) for r in results)

    def test_search_result_has_chunk(self, in_memory_indexer):
        in_memory_indexer.add_chunks([make_chunk(chunk_id="x001")])
        results = in_memory_indexer.search("hello")
        assert results[0].chunk is not None
        assert isinstance(results[0].chunk, Chunk)

    def test_search_score_range(self, in_memory_indexer):
        in_memory_indexer.add_chunks([make_chunk(chunk_id="s001")])
        results = in_memory_indexer.search("test query")
        for r in results:
            assert 0.0 <= r.score <= 1.0

    def test_search_n_results_limit(self, in_memory_indexer):
        chunks = [make_chunk(chunk_id=f"r{i:03d}", content=f"content {i}") for i in range(10)]
        in_memory_indexer.add_chunks(chunks)
        results = in_memory_indexer.search("query", n_results=3)
        assert len(results) <= 3

    def test_search_on_empty_index(self, in_memory_indexer):
        # Should return empty list, not raise
        results = in_memory_indexer.search("anything")
        assert results == []

    def test_search_preserves_metadata(self, in_memory_indexer):
        chunk = make_chunk(
            file_path="special.ts",
            start_line=42,
            end_line=55,
            language="typescript",
            chunk_id="m001",
        )
        in_memory_indexer.add_chunks([chunk])
        results = in_memory_indexer.search("query")
        found = results[0].chunk
        assert found.file_path == "special.ts"
        assert found.start_line == 42
        assert found.end_line == 55
        assert found.language == "typescript"


class TestClear:
    def test_clear_removes_all_chunks(self, in_memory_indexer):
        chunks = [make_chunk(chunk_id=f"cl{i}") for i in range(5)]
        in_memory_indexer.add_chunks(chunks)
        assert in_memory_indexer.count() == 5
        in_memory_indexer.clear()
        assert in_memory_indexer.count() == 0

    def test_can_add_after_clear(self, in_memory_indexer):
        in_memory_indexer.add_chunks([make_chunk(chunk_id="pre")])
        in_memory_indexer.clear()
        in_memory_indexer.add_chunks([make_chunk(chunk_id="post")])
        assert in_memory_indexer.count() == 1
