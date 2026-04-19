"""Unit tests for :mod:`playwright_god.spec_index`."""

from __future__ import annotations

from pathlib import Path

import pytest

from playwright_god.spec_index import (
    SpecEntry,
    SpecIndex,
    extract_heuristic_node_ids,
    parse_pg_tags,
)


def _write(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# @pg-tags parsing
# ---------------------------------------------------------------------------


def test_parse_pg_tags_extracts_node_ids():
    content = """\
// @pg-tags route:GET:/login action:src/Login.tsx:42#submit
import { test } from '@playwright/test';
"""
    node_ids, pinned = parse_pg_tags(content)
    assert node_ids == ["route:GET:/login", "action:src/Login.tsx:42#submit"]
    assert pinned is False


def test_parse_pg_tags_detects_pin():
    content = """\
// @pg-pin
// @pg-tags route:GET:/admin
import { test } from '@playwright/test';
"""
    node_ids, pinned = parse_pg_tags(content)
    assert node_ids == ["route:GET:/admin"]
    assert pinned is True


def test_parse_pg_tags_pin_only():
    content = """\
// @pg-pin
import { test } from '@playwright/test';
"""
    node_ids, pinned = parse_pg_tags(content)
    assert node_ids == []
    assert pinned is True


def test_parse_pg_tags_case_insensitive():
    content = "// @PG-TAGS Route:POST:/api\n"
    node_ids, pinned = parse_pg_tags(content)
    assert "Route:POST:/api" in node_ids


def test_parse_pg_tags_none_found():
    content = "import { test } from '@playwright/test';\ntest('x', () => {});\n"
    node_ids, pinned = parse_pg_tags(content)
    assert node_ids == []
    assert pinned is False


def test_parse_pg_tags_skips_empty_lines():
    """Empty lines in the header should be skipped without error."""
    content = """\

// First line is blank

// @pg-tags route:GET:/users

import { test } from '@playwright/test';
"""
    node_ids, pinned = parse_pg_tags(content)
    assert "route:GET:/users" in node_ids
    assert pinned is False


# ---------------------------------------------------------------------------
# Heuristic extraction
# ---------------------------------------------------------------------------


def test_heuristic_extracts_goto_urls():
    content = """\
test('login', async ({ page }) => {
    await page.goto("/login");
    await page.goto('/dashboard');
});
"""
    node_ids = extract_heuristic_node_ids(content)
    assert "route:GET:/login" in node_ids
    assert "route:GET:/dashboard" in node_ids


def test_heuristic_extracts_concatenated_urls():
    content = """\
test('login', async ({ page }) => {
    await page.goto(baseURL + "/profile");
});
"""
    node_ids = extract_heuristic_node_ids(content)
    assert "route:GET:/profile" in node_ids


def test_heuristic_ignores_non_slash_paths():
    content = """\
await page.goto("http://example.com");
"""
    node_ids = extract_heuristic_node_ids(content)
    assert node_ids == []


def test_heuristic_with_flow_graph_filters_invalid():
    from playwright_god.flow_graph import FlowGraph, Route

    fg = FlowGraph.from_iterables([
        Route(method="GET", path="/valid"),
    ])
    content = 'await page.goto("/valid");\nawait page.goto("/invalid");'
    node_ids = extract_heuristic_node_ids(content, flow_graph=fg)
    assert "route:GET:/valid" in node_ids
    assert "route:GET:/invalid" not in node_ids


# ---------------------------------------------------------------------------
# SpecEntry
# ---------------------------------------------------------------------------


def test_spec_entry_roundtrip():
    entry = SpecEntry(
        path="tests/login.spec.ts",
        node_ids=("route:GET:/login",),
        content_hash="abc123",
        pinned=True,
        tag_source=True,
    )
    d = entry.to_dict()
    restored = SpecEntry.from_dict(d)
    assert restored == entry


# ---------------------------------------------------------------------------
# SpecIndex building
# ---------------------------------------------------------------------------


def test_spec_index_build_with_tags(tmp_path: Path):
    _write(
        tmp_path,
        "login.spec.ts",
        "// @pg-tags route:GET:/login\nimport { test } from '@playwright/test';\n",
    )
    index = SpecIndex.build(tmp_path)
    assert len(index) == 1
    entry = index.get("login.spec.ts")
    assert entry is not None
    assert "route:GET:/login" in entry.node_ids
    assert entry.tag_source is True


def test_spec_index_build_with_heuristics(tmp_path: Path):
    _write(
        tmp_path,
        "dashboard.spec.ts",
        "test('x', async ({page}) => { await page.goto('/dashboard'); });\n",
    )
    index = SpecIndex.build(tmp_path)
    entry = index.get("dashboard.spec.ts")
    assert entry is not None
    assert "route:GET:/dashboard" in entry.node_ids
    assert entry.tag_source is False


def test_spec_index_build_caches_by_hash(tmp_path: Path):
    spec_path = _write(
        tmp_path,
        "cached.spec.ts",
        "// @pg-tags route:GET:/cached\ntest('x', () => {});\n",
    )
    cache_path = tmp_path / "cache" / "spec_index.json"

    # First build
    index1 = SpecIndex.build(tmp_path, cache_path=cache_path)
    assert cache_path.exists()

    # Second build should use cache
    index2 = SpecIndex.build(tmp_path, cache_path=cache_path)
    assert index1.get("cached.spec.ts").content_hash == index2.get("cached.spec.ts").content_hash


def test_spec_index_cache_invalidated_on_change(tmp_path: Path):
    spec_path = _write(
        tmp_path,
        "changing.spec.ts",
        "// @pg-tags route:GET:/v1\ntest('x', () => {});\n",
    )
    cache_path = tmp_path / "cache" / "spec_index.json"

    # First build
    index1 = SpecIndex.build(tmp_path, cache_path=cache_path)
    hash1 = index1.get("changing.spec.ts").content_hash

    # Modify the file
    spec_path.write_text("// @pg-tags route:GET:/v2\ntest('y', () => {});\n")

    # Second build should detect change
    index2 = SpecIndex.build(tmp_path, cache_path=cache_path)
    hash2 = index2.get("changing.spec.ts").content_hash
    assert hash1 != hash2
    assert "route:GET:/v2" in index2.get("changing.spec.ts").node_ids


def test_spec_index_handles_corrupt_cache(tmp_path: Path):
    """Corrupt cache should be ignored, not crash."""
    _write(
        tmp_path,
        "test.spec.ts",
        "// @pg-tags route:GET:/test\ntest('x', () => {});\n",
    )
    cache_path = tmp_path / "cache" / "spec_index.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    # Write corrupt JSON
    cache_path.write_text("{ invalid json }", encoding="utf-8")

    # Build should succeed despite corrupt cache
    index = SpecIndex.build(tmp_path, cache_path=cache_path)
    assert len(index) == 1
    assert "route:GET:/test" in index.get("test.spec.ts").node_ids


def test_spec_index_specs_covering():
    index = SpecIndex(entries={
        "a.spec.ts": SpecEntry("a.spec.ts", ("route:GET:/x", "route:GET:/y"), "h1"),
        "b.spec.ts": SpecEntry("b.spec.ts", ("route:GET:/x",), "h2"),
    })
    covering = index.specs_covering("route:GET:/x")
    assert "a.spec.ts" in covering
    assert "b.spec.ts" in covering
    assert index.specs_covering("route:GET:/z") == []


def test_spec_index_json_roundtrip():
    index = SpecIndex(entries={
        "test.spec.ts": SpecEntry("test.spec.ts", ("route:GET:/test",), "hash1"),
    })
    json_str = index.to_json()
    restored = SpecIndex.from_json(json_str)
    assert len(restored) == 1
    assert restored.get("test.spec.ts").node_ids == ("route:GET:/test",)


def test_spec_index_divergence_logged(tmp_path: Path, caplog):
    """When tags and heuristics disagree, tags win and divergence is logged."""
    import logging

    _write(
        tmp_path,
        "diverge.spec.ts",
        '// @pg-tags route:GET:/a\nawait page.goto("/b");\n',
    )
    with caplog.at_level(logging.DEBUG):
        index = SpecIndex.build(tmp_path)

    entry = index.get("diverge.spec.ts")
    assert "route:GET:/a" in entry.node_ids
    assert "route:GET:/b" not in entry.node_ids
    # Check divergence was logged
    assert any("diverge" in r.message.lower() for r in caplog.records)


def test_spec_index_handles_unreadable_files(tmp_path: Path):
    # Create a directory with the same name as a spec (edge case)
    (tmp_path / "fake.spec.ts").mkdir()
    index = SpecIndex.build(tmp_path)
    assert len(index) == 0


def test_spec_index_iteration():
    entry1 = SpecEntry("a.spec.ts", (), "h1")
    entry2 = SpecEntry("b.spec.ts", (), "h2")
    index = SpecIndex(entries={"a.spec.ts": entry1, "b.spec.ts": entry2})
    entries = list(index)
    assert len(entries) == 2
