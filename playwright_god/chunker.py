"""File chunker: splits FileInfo objects into overlapping text chunks for RAG."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Sequence

from .crawler import FileInfo


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Chunk:
    """A contiguous slice of a source file, suitable for embedding."""

    file_path: str    # relative path of the source file
    content: str      # text content of this chunk
    start_line: int   # 1-indexed first line (inclusive)
    end_line: int     # 1-indexed last line (inclusive)
    language: str     # language of the source file
    chunk_id: str     # stable unique identifier

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"Chunk(file_path={self.file_path!r}, "
            f"lines={self.start_line}-{self.end_line}, "
            f"language={self.language!r})"
        )

    @classmethod
    def _make_id(cls, file_path: str, start_line: int, end_line: int) -> str:
        """Create a stable, unique chunk identifier."""
        key = f"{file_path}:{start_line}:{end_line}"
        return hashlib.sha1(key.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Chunker
# ---------------------------------------------------------------------------


class FileChunker:
    """Splits :class:`~playwright_god.crawler.FileInfo` objects into
    overlapping line-based :class:`Chunk` objects.

    Parameters
    ----------
    chunk_size:
        Maximum number of lines per chunk.
    overlap:
        Number of lines to repeat at the start of the next chunk (sliding
        window).  Must be less than *chunk_size*.
    """

    def __init__(self, chunk_size: int = 80, overlap: int = 10) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be a positive integer")
        if overlap < 0:
            raise ValueError("overlap must be a non-negative integer")
        if overlap >= chunk_size:
            raise ValueError("overlap must be less than chunk_size")
        self.chunk_size = chunk_size
        self.overlap = overlap

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def chunk_file(self, file_info: FileInfo) -> list[Chunk]:
        """Return a list of :class:`Chunk` objects for a single file.

        If the file has no content or only whitespace, an empty list is
        returned.
        """
        lines = file_info.content.splitlines()
        if not lines:
            return []

        chunks: list[Chunk] = []
        step = self.chunk_size - self.overlap
        start = 0  # 0-indexed

        while start < len(lines):
            end = min(start + self.chunk_size, len(lines))
            chunk_lines = lines[start:end]
            content = "\n".join(chunk_lines)

            # Prepend a file-path header so each chunk carries its own
            # provenance even when retrieved in isolation.
            header = f"# File: {file_info.path} (lines {start + 1}-{end})\n"
            full_content = header + content

            chunk = Chunk(
                file_path=file_info.path,
                content=full_content,
                start_line=start + 1,
                end_line=end,
                language=file_info.language,
                chunk_id=Chunk._make_id(file_info.path, start + 1, end),
            )
            chunks.append(chunk)

            if end == len(lines):
                break
            start += step

        return chunks

    def chunk_files(self, files: Sequence[FileInfo]) -> list[Chunk]:
        """Chunk all files and return a flat list of :class:`Chunk` objects."""
        result: list[Chunk] = []
        for file_info in files:
            result.extend(self.chunk_file(file_info))
        return result
