"""Unit tests for playwright_god.memory_map."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from playwright_god.chunker import Chunk
from playwright_god.memory_map import (
    build_memory_map,
    format_memory_map_for_prompt,
    load_memory_map,
    save_memory_map,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_chunk(
    file_path: str,
    start_line: int,
    end_line: int,
    language: str = "typescript",
    chunk_id: str | None = None,
) -> Chunk:
    cid = chunk_id or Chunk._make_id(file_path, start_line, end_line)
    return Chunk(
        file_path=file_path,
        content=f"# File: {file_path} (lines {start_line}-{end_line})\ncontent",
        start_line=start_line,
        end_line=end_line,
        language=language,
        chunk_id=cid,
    )


# ---------------------------------------------------------------------------
# build_memory_map
# ---------------------------------------------------------------------------


class TestBuildMemoryMap:
    def test_empty_chunks_returns_valid_map(self):
        result = build_memory_map([])
        assert result["total_files"] == 0
        assert result["total_chunks"] == 0
        assert result["languages"] == {}
        assert result["files"] == []
        assert "generated_at" in result

    def test_single_chunk(self):
        chunks = [_make_chunk("src/app.ts", 1, 80)]
        result = build_memory_map(chunks)
        assert result["total_files"] == 1
        assert result["total_chunks"] == 1
        assert result["languages"] == {"typescript": 1}
        assert len(result["files"]) == 1
        file_entry = result["files"][0]
        assert file_entry["path"] == "src/app.ts"
        assert file_entry["language"] == "typescript"
        assert len(file_entry["chunks"]) == 1
        assert file_entry["chunks"][0]["start_line"] == 1
        assert file_entry["chunks"][0]["end_line"] == 80

    def test_multiple_chunks_same_file(self):
        chunks = [
            _make_chunk("src/app.ts", 1, 80),
            _make_chunk("src/app.ts", 71, 150),
        ]
        result = build_memory_map(chunks)
        assert result["total_files"] == 1
        assert result["total_chunks"] == 2
        file_entry = result["files"][0]
        assert len(file_entry["chunks"]) == 2
        # Chunks ordered by start_line
        assert file_entry["chunks"][0]["start_line"] == 1
        assert file_entry["chunks"][1]["start_line"] == 71

    def test_multiple_files_sorted(self):
        chunks = [
            _make_chunk("src/z.ts", 1, 80),
            _make_chunk("src/a.ts", 1, 80),
        ]
        result = build_memory_map(chunks)
        assert result["total_files"] == 2
        paths = [f["path"] for f in result["files"]]
        assert paths == ["src/a.ts", "src/z.ts"]

    def test_language_counts(self):
        chunks = [
            _make_chunk("src/a.ts", 1, 80, language="typescript"),
            _make_chunk("src/b.ts", 1, 80, language="typescript"),
            _make_chunk("src/c.py", 1, 80, language="python"),
        ]
        result = build_memory_map(chunks)
        assert result["languages"]["typescript"] == 2
        assert result["languages"]["python"] == 1

    def test_generated_at_is_iso8601(self):
        result = build_memory_map([])
        from datetime import datetime
        # Should parse without error
        datetime.fromisoformat(result["generated_at"])

    def test_chunk_ids_preserved(self):
        chunk = _make_chunk("src/app.ts", 1, 80, chunk_id="myid123")
        result = build_memory_map([chunk])
        assert result["files"][0]["chunks"][0]["chunk_id"] == "myid123"


# ---------------------------------------------------------------------------
# save_memory_map / load_memory_map
# ---------------------------------------------------------------------------


class TestSaveLoadMemoryMap:
    def test_round_trip(self, tmp_path):
        chunks = [_make_chunk("src/app.ts", 1, 80)]
        map_data = build_memory_map(chunks)
        dest = str(tmp_path / "memory_map.json")

        save_memory_map(map_data, dest)
        loaded = load_memory_map(dest)

        assert loaded["total_files"] == map_data["total_files"]
        assert loaded["total_chunks"] == map_data["total_chunks"]
        assert loaded["files"] == map_data["files"]

    def test_save_creates_parent_dirs(self, tmp_path):
        dest = str(tmp_path / "sub" / "dir" / "map.json")
        save_memory_map({"total_files": 0, "total_chunks": 0, "languages": {}, "files": []}, dest)
        assert Path(dest).exists()

    def test_save_writes_valid_json(self, tmp_path):
        dest = str(tmp_path / "map.json")
        save_memory_map({"key": "value"}, dest)
        data = json.loads(Path(dest).read_text())
        assert data == {"key": "value"}

    def test_load_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="Memory map"):
            load_memory_map(str(tmp_path / "nonexistent.json"))

    def test_load_invalid_json_raises(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("not-json", encoding="utf-8")
        with pytest.raises(ValueError, match="Invalid JSON"):
            load_memory_map(str(bad))


# ---------------------------------------------------------------------------
# format_memory_map_for_prompt
# ---------------------------------------------------------------------------


class TestFormatMemoryMapForPrompt:
    def test_contains_header(self):
        result = format_memory_map_for_prompt({"total_files": 0, "total_chunks": 0, "languages": {}, "files": []})
        assert "Indexed codebase memory map" in result

    def test_contains_file_paths(self):
        chunks = [_make_chunk("src/auth.ts", 1, 80)]
        map_data = build_memory_map(chunks)
        result = format_memory_map_for_prompt(map_data)
        assert "src/auth.ts" in result
        assert "typescript" in result

    def test_contains_line_ranges(self):
        chunks = [_make_chunk("src/app.ts", 1, 80), _make_chunk("src/app.ts", 71, 150)]
        map_data = build_memory_map(chunks)
        result = format_memory_map_for_prompt(map_data)
        assert "1-80" in result
        assert "71-150" in result

    def test_contains_totals(self):
        chunks = [_make_chunk("a.ts", 1, 10), _make_chunk("b.ts", 1, 10)]
        result = format_memory_map_for_prompt(build_memory_map(chunks))
        assert "2" in result  # total files

    def test_empty_map(self):
        result = format_memory_map_for_prompt({"total_files": 0, "total_chunks": 0, "languages": {}, "files": []})
        assert "0" in result

    def test_language_summary_sorted_by_frequency(self):
        chunks = [
            _make_chunk("a.ts", 1, 10, language="typescript"),
            _make_chunk("b.ts", 1, 10, language="typescript"),
            _make_chunk("c.py", 1, 10, language="python"),
        ]
        result = format_memory_map_for_prompt(build_memory_map(chunks))
        ts_pos = result.index("typescript")
        py_pos = result.index("python")
        assert ts_pos < py_pos  # typescript (2) appears before python (1)
