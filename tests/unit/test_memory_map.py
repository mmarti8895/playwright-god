"""Unit tests for playwright_god.memory_map."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from playwright_god.chunker import Chunk
from playwright_god.feature_map import infer_repository_feature_map
from playwright_god.memory_map import (
    build_memory_map,
    format_memory_map_for_prompt,
    load_memory_map,
    save_memory_map,
    with_flow_graph,
    with_repo_profile,
)
from playwright_god.flow_graph import Evidence, FlowGraph, Route
from playwright_god.repo_profile import BlindSpot, RepoProfile, RuntimeTarget, StartupCandidate


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

    def test_includes_feature_metadata_when_provided(self, simple_file_info):
        chunk = Chunk(
            file_path=simple_file_info.path,
            content=simple_file_info.content,
            start_line=1,
            end_line=3,
            language=simple_file_info.language,
            chunk_id="feature-id",
        )
        feature_map = infer_repository_feature_map(
            [simple_file_info],
            chunks=[chunk],
            source_root="/repo",
            generated_at="2026-04-11T00:00:00+00:00",
        )
        result = build_memory_map([chunk], repository_feature_map=feature_map)
        assert result["schema_version"] == "2.1"
        assert "features" in result
        assert "test_opportunities" in result

    def test_includes_repo_profile_metadata_when_provided(self):
        profile = RepoProfile(
            source_root="/repo",
            languages={"python": 1},
            frameworks=("fastapi",),
            archetype="api-service",
            confidence=0.8,
            startup_candidates=(
                StartupCandidate(
                    command="python -m uvicorn app:app",
                    source="pyproject:uvicorn",
                    base_url="http://127.0.0.1:8000",
                    confidence=0.8,
                ),
            ),
            runtime_targets=(
                RuntimeTarget(
                    kind="route",
                    method="GET",
                    path="/healthz",
                    base_url="http://127.0.0.1:8000",
                    confidence=0.75,
                ),
            ),
            blind_spots=(BlindSpot(category="extractor", summary="example"),),
        )
        result = build_memory_map([], repo_profile=profile)
        assert result["schema_version"] == "2.3"
        assert result["repo_profile"]["archetype"] == "api-service"
        assert result["startup_candidates"][0]["command"] == "python -m uvicorn app:app"


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

    def test_invalid_language_counts_are_skipped(self):
        malformed_map = {
            "total_files": 2,
            "total_chunks": 2,
            "languages": {"typescript": "two", "python": 1, "go": None},
            "files": [],
        }
        result = format_memory_map_for_prompt(malformed_map)
        assert "python (1)" in result
        assert "typescript" not in result
        assert "go" not in result

    def test_malformed_chunk_missing_line_keys_does_not_crash(self):
        """format_memory_map_for_prompt should not raise for chunks missing line keys."""
        malformed_map = {
            "total_files": 1,
            "total_chunks": 1,
            "languages": {"typescript": 1},
            "files": [
                {
                    "path": "src/app.ts",
                    "language": "typescript",
                    "chunks": [{"chunk_id": "x1"}],  # no start_line / end_line
                }
            ],
        }
        result = format_memory_map_for_prompt(malformed_map)
        assert "src/app.ts" in result
        # Missing keys fall back to "?" placeholder
        assert "?-?" in result

    def test_malformed_chunk_non_dict_skipped(self):
        """Non-dict chunk entries are skipped gracefully."""
        malformed_map = {
            "total_files": 1,
            "total_chunks": 1,
            "languages": {"typescript": 1},
            "files": [
                {
                    "path": "src/app.ts",
                    "language": "typescript",
                    "chunks": ["not-a-dict"],
                }
            ],
        }
        result = format_memory_map_for_prompt(malformed_map)
        assert "src/app.ts" in result
        assert "(no chunks)" in result

    def test_non_numeric_language_counts_are_skipped(self):
        result = format_memory_map_for_prompt(
            {"total_files": 0, "total_chunks": 0, "languages": {"python": "two"}, "files": []}
        )
        assert "Languages   : n/a" in result

    def test_non_dict_file_entries_are_skipped(self):
        result = format_memory_map_for_prompt(
            {"total_files": 1, "total_chunks": 1, "languages": {}, "files": ["bad-entry"]}
        )
        assert "File index" in result

    def test_feature_sections_render_when_present(self):
        feature_map = {
            "features": [
                {
                    "feature_id": "authentication",
                    "name": "Authentication",
                    "confidence": 0.9,
                    "summary": "Sign-in workflows",
                    "artifacts": [{"file_path": "src/auth.py"}],
                }
            ],
            "correlations": [
                {
                    "source_feature_id": "authentication",
                    "target_feature_id": "navigation",
                    "relationship_type": "shared-artifact",
                }
            ],
            "test_opportunities": [
                {
                    "feature_id": "authentication",
                    "title": "User can sign in",
                    "confidence": 0.9,
                }
            ],
        }
        result = format_memory_map_for_prompt(
            {
                "total_files": 0,
                "total_chunks": 0,
                "languages": {},
                "files": [],
                **feature_map,
            }
        )
        assert "Feature areas" in result
        assert "Suggested test opportunities" in result

    def test_repo_profile_sections_render_when_present(self):
        result = format_memory_map_for_prompt(
            {
                "total_files": 0,
                "total_chunks": 0,
                "languages": {},
                "files": [],
                "repo_profile": {
                    "archetype": "spa",
                    "confidence": 0.8,
                    "frameworks": ["react"],
                    "startup_candidates": [{"command": "npm run dev", "source": "package.json:dev"}],
                    "runtime_targets": [{"method": "GET", "path": "/", "kind": "route"}],
                    "blind_spots": [{"summary": "No runtime probe was attempted."}],
                },
            }
        )
        assert "Repository profile" in result
        assert "Startup candidates" in result
        assert "Blind spots" in result

    def test_feature_sections_skip_non_dict_entries_and_support_dict_payloads(self):
        result = format_memory_map_for_prompt(
            {
                "total_files": 0,
                "total_chunks": 0,
                "languages": {},
                "files": [],
                "features": ["bad-feature", {"feature_id": "docs"}],
                "correlations": ["bad-correlation", {"source_feature_id": "a", "target_feature_id": "b"}],
                "test_opportunities": ["bad-opportunity", {"feature_id": "a"}],
            }
        )
        assert "docs" in result
        assert "a -> b [related]" in result
        assert "a: Unknown scenario [?]" in result

    def test_build_memory_map_accepts_feature_dict_payload(self):
        result = build_memory_map(
            [],
            repository_feature_map={
                "schema_version": "2.1",
                "features": [],
                "correlations": [],
                "test_opportunities": [],
                "source_root": "/repo",
            },
        )
        assert result["schema_version"] == "2.1"


# ---------------------------------------------------------------------------
# Schema 2.1: coverage augmentation
# ---------------------------------------------------------------------------


class _StubFC:
    def __init__(self, covered, uncovered):
        self.covered_lines = covered
        self.uncovered_lines = uncovered


class _StubReport:
    def __init__(self, files):
        self.files = files


class TestSchema21Coverage:
    def test_with_coverage_bumps_to_21_and_adds_field(self):
        from playwright_god.memory_map import with_coverage

        base = {"schema_version": "2.0", "files": []}
        report = _StubReport(
            {"src/a.ts": _StubFC([1, 2, 3], [4, 5]), "src/b.py": _StubFC([1], [])}
        )
        out = with_coverage(base, report)
        assert out["schema_version"] == "2.1"
        assert out["coverage"]["summary"]["files"] == 2
        assert out["coverage"]["summary"]["covered_lines"] == 4
        assert out["coverage"]["summary"]["uncovered_lines"] == 2
        a_entry = next(f for f in out["coverage"]["files"] if f["path"] == "src/a.ts")
        assert a_entry["covered_lines"] == [1, 2, 3]
        assert a_entry["uncovered_lines"] == [4, 5]
        assert base["schema_version"] == "2.0"

    def test_load_memory_map_accepts_2x_and_defaults_coverage(self, tmp_path):
        from playwright_god.memory_map import load_memory_map

        path = tmp_path / "m.json"
        path.write_text(
            json.dumps({"schema_version": "2.1", "files": [], "total_files": 0,
                        "total_chunks": 0, "languages": {}}),
            encoding="utf-8",
        )
        loaded = load_memory_map(str(path))
        assert loaded["schema_version"] == "2.1"
        assert loaded["coverage"] is None

    def test_load_memory_map_rejects_non_2x(self, tmp_path):
        from playwright_god.memory_map import load_memory_map

        path = tmp_path / "m.json"
        path.write_text(json.dumps({"schema_version": "3.0"}), encoding="utf-8")
        with pytest.raises(ValueError, match="2.x"):
            load_memory_map(str(path))

    def test_with_coverage_roundtrip_via_disk(self, tmp_path):
        from playwright_god.memory_map import with_coverage

        base = build_memory_map([])
        report = _StubReport({"src/a.ts": _StubFC([1, 2], [3])})
        annotated = with_coverage(base, report)
        dest = tmp_path / "m.json"
        save_memory_map(annotated, str(dest))
        loaded = load_memory_map(str(dest))
        assert loaded["coverage"]["summary"]["files"] == 1
        assert loaded["schema_version"] == "2.1"


# ---------------------------------------------------------------------------
# Schema 2.2: flow graph
# ---------------------------------------------------------------------------


class TestFlowGraphSchema22:
    def _graph(self) -> FlowGraph:
        return FlowGraph.from_iterables(
            nodes=[Route(method="GET", path="/x", evidence=(Evidence("a.py", (1, 1)),))]
        )

    def test_with_flow_graph_bumps_schema_to_22(self):
        base = build_memory_map([])
        out = with_flow_graph(base, self._graph())
        assert out["schema_version"] == "2.2"
        assert out["flow_graph"]["nodes"][0]["id"] == "route:GET:/x"

    def test_with_flow_graph_none_clears_field(self):
        base = build_memory_map([])
        out = with_flow_graph(base, None)
        assert out["flow_graph"] is None
        assert out["schema_version"] == "2.2"

    def test_load_21_map_defaults_flow_graph_none(self, tmp_path):
        path = tmp_path / "m.json"
        path.write_text(
            json.dumps({"schema_version": "2.1", "files": []}), encoding="utf-8"
        )
        loaded = load_memory_map(str(path))
        assert loaded["flow_graph"] is None
        assert loaded["coverage"] is None

    def test_22_roundtrip_via_disk(self, tmp_path):
        base = build_memory_map([])
        annotated = with_flow_graph(base, self._graph())
        dest = tmp_path / "m.json"
        save_memory_map(annotated, str(dest))
        loaded = load_memory_map(str(dest))
        assert loaded["schema_version"] == "2.2"
        assert loaded["flow_graph"]["nodes"][0]["id"] == "route:GET:/x"
        # FlowGraph rebuilt from on-disk payload survives the round-trip.
        rebuilt = FlowGraph.from_dict(loaded["flow_graph"])
        assert rebuilt.routes[0].id == "route:GET:/x"

    def test_with_flow_graph_accepts_dict_payload(self):
        base = build_memory_map([])
        graph_dict = self._graph().to_dict()
        out = with_flow_graph(base, graph_dict)
        assert out["flow_graph"] == graph_dict

    def test_higher_schema_not_downgraded(self):
        base = {"schema_version": "2.5"}
        out = with_flow_graph(base, self._graph())
        assert out["schema_version"] == "2.5"


class TestRepoProfileSchema23:
    def test_with_repo_profile_bumps_schema(self):
        base = build_memory_map([])
        out = with_repo_profile(
            base,
            {
                "source_root": "/repo",
                "archetype": "spa",
                "frameworks": ["react"],
                "runtime_targets": [],
                "startup_candidates": [],
                "environment_profile": {},
                "auth_profile": {},
                "bootstrap_steps": [],
                "state_recipes": [],
            },
        )
        assert out["schema_version"] == "2.3"
        assert out["repo_profile"]["archetype"] == "spa"

    def test_load_map_defaults_repo_profile_keys(self, tmp_path):
        path = tmp_path / "m.json"
        path.write_text(json.dumps({"schema_version": "2.2", "files": []}), encoding="utf-8")
        loaded = load_memory_map(str(path))
        assert loaded["repo_profile"] is None
        assert loaded["startup_candidates"] == []
        assert loaded["runtime_targets"] == []
