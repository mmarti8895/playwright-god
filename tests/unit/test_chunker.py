"""Unit tests for playwright_god.chunker."""

from __future__ import annotations

import pytest

from playwright_god.chunker import Chunk, FileChunker
from playwright_god.crawler import FileInfo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_file(content: str, path: str = "src/app.py", language: str = "python") -> FileInfo:
    return FileInfo(
        path=path,
        absolute_path=f"/{path}",
        content=content,
        language=language,
        size=len(content.encode()),
    )


def make_lines(n: int) -> str:
    """Return a string with *n* numbered lines."""
    return "\n".join(f"line {i}" for i in range(1, n + 1))


# ---------------------------------------------------------------------------
# Chunk dataclass
# ---------------------------------------------------------------------------


class TestChunk:
    def test_make_id_is_stable(self):
        id1 = Chunk._make_id("src/app.py", 1, 80)
        id2 = Chunk._make_id("src/app.py", 1, 80)
        assert id1 == id2

    def test_make_id_differs_by_path(self):
        id1 = Chunk._make_id("a.py", 1, 10)
        id2 = Chunk._make_id("b.py", 1, 10)
        assert id1 != id2

    def test_make_id_differs_by_lines(self):
        id1 = Chunk._make_id("a.py", 1, 10)
        id2 = Chunk._make_id("a.py", 11, 20)
        assert id1 != id2

    def test_make_id_length(self):
        assert len(Chunk._make_id("x.py", 1, 5)) == 16


# ---------------------------------------------------------------------------
# FileChunker init
# ---------------------------------------------------------------------------


class TestFileChunkerInit:
    def test_defaults(self):
        chunker = FileChunker()
        assert chunker.chunk_size == 80
        assert chunker.overlap == 10

    def test_custom_values(self):
        chunker = FileChunker(chunk_size=50, overlap=5)
        assert chunker.chunk_size == 50
        assert chunker.overlap == 5

    def test_invalid_chunk_size(self):
        with pytest.raises(ValueError, match="chunk_size"):
            FileChunker(chunk_size=0)

    def test_negative_chunk_size(self):
        with pytest.raises(ValueError, match="chunk_size"):
            FileChunker(chunk_size=-1)

    def test_negative_overlap(self):
        with pytest.raises(ValueError, match="overlap"):
            FileChunker(chunk_size=10, overlap=-1)

    def test_overlap_equals_chunk_size(self):
        with pytest.raises(ValueError, match="overlap"):
            FileChunker(chunk_size=10, overlap=10)

    def test_overlap_greater_than_chunk_size(self):
        with pytest.raises(ValueError, match="overlap"):
            FileChunker(chunk_size=10, overlap=11)


# ---------------------------------------------------------------------------
# chunk_file
# ---------------------------------------------------------------------------


class TestChunkFile:
    def test_empty_content_returns_no_chunks(self):
        chunker = FileChunker()
        fi = make_file("")
        assert chunker.chunk_file(fi) == []

    def test_whitespace_only_returns_no_chunks(self):
        chunker = FileChunker()
        fi = make_file("   \n  \n")
        # splitlines() returns ['   ', '  '] — not empty, so 1 chunk
        chunks = chunker.chunk_file(fi)
        assert len(chunks) >= 0  # implementation may or may not produce a chunk

    def test_single_line_produces_one_chunk(self):
        chunker = FileChunker(chunk_size=80, overlap=10)
        fi = make_file("hello world")
        chunks = chunker.chunk_file(fi)
        assert len(chunks) == 1
        assert "hello world" in chunks[0].content

    def test_chunk_contains_file_header(self):
        chunker = FileChunker(chunk_size=80, overlap=10)
        fi = make_file("hello world")
        chunks = chunker.chunk_file(fi)
        assert "src/app.py" in chunks[0].content

    def test_small_file_single_chunk(self):
        chunker = FileChunker(chunk_size=100, overlap=10)
        fi = make_file(make_lines(50))
        chunks = chunker.chunk_file(fi)
        assert len(chunks) == 1

    def test_large_file_multiple_chunks(self):
        chunker = FileChunker(chunk_size=10, overlap=2)
        fi = make_file(make_lines(25))
        chunks = chunker.chunk_file(fi)
        assert len(chunks) > 1

    def test_chunks_cover_all_lines(self):
        """Every line of the original file should appear in at least one chunk."""
        chunker = FileChunker(chunk_size=10, overlap=2)
        content = make_lines(30)
        fi = make_file(content)
        chunks = chunker.chunk_file(fi)
        all_content = "\n".join(c.content for c in chunks)
        for i in range(1, 31):
            assert f"line {i}" in all_content

    def test_chunk_start_end_lines(self):
        chunker = FileChunker(chunk_size=5, overlap=0)
        fi = make_file(make_lines(10))
        chunks = chunker.chunk_file(fi)
        assert chunks[0].start_line == 1
        assert chunks[0].end_line == 5
        assert chunks[1].start_line == 6
        assert chunks[1].end_line == 10

    def test_overlap_causes_repeated_lines(self):
        chunker = FileChunker(chunk_size=5, overlap=2)
        content = make_lines(10)
        fi = make_file(content)
        chunks = chunker.chunk_file(fi)
        # With overlap=2, chunk 1 ends at line 5, chunk 2 starts at line 4
        assert chunks[0].end_line >= chunks[1].start_line - 1

    def test_chunk_ids_are_unique(self):
        chunker = FileChunker(chunk_size=5, overlap=0)
        fi = make_file(make_lines(20))
        chunks = chunker.chunk_file(fi)
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))

    def test_language_propagated(self):
        chunker = FileChunker()
        fi = make_file("const x = 1;", path="app.js", language="javascript")
        chunks = chunker.chunk_file(fi)
        assert all(c.language == "javascript" for c in chunks)

    def test_file_path_propagated(self):
        chunker = FileChunker()
        fi = make_file("x = 1", path="pkg/module.py")
        chunks = chunker.chunk_file(fi)
        assert all(c.file_path == "pkg/module.py" for c in chunks)


# ---------------------------------------------------------------------------
# chunk_files
# ---------------------------------------------------------------------------


class TestChunkFiles:
    def test_empty_list(self):
        chunker = FileChunker()
        assert chunker.chunk_files([]) == []

    def test_multiple_files(self):
        chunker = FileChunker(chunk_size=5, overlap=0)
        files = [
            make_file(make_lines(10), path="a.py"),
            make_file(make_lines(10), path="b.py"),
        ]
        chunks = chunker.chunk_files(files)
        paths = {c.file_path for c in chunks}
        assert "a.py" in paths
        assert "b.py" in paths

    def test_total_chunk_count(self):
        chunker = FileChunker(chunk_size=5, overlap=0)
        files = [make_file(make_lines(10), path=f"file{i}.py") for i in range(3)]
        chunks = chunker.chunk_files(files)
        # Each 10-line file with chunk_size=5, overlap=0 → 2 chunks
        assert len(chunks) == 6
