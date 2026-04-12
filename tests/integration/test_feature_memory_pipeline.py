"""Integration tests for feature-aware memory maps and summaries."""

from __future__ import annotations

from playwright_god.chunker import FileChunker
from playwright_god.crawler import RepositoryCrawler
from playwright_god.feature_map import format_feature_summary, infer_repository_feature_map
from playwright_god.memory_map import (
    build_memory_map,
    format_memory_map_for_prompt,
    load_memory_map,
    save_memory_map,
)


def _build_feature_map(repo_path: str):
    crawler = RepositoryCrawler()
    files = crawler.crawl(repo_path)
    chunker = FileChunker(chunk_size=30, overlap=5)
    chunks = chunker.chunk_files(files)
    feature_map = infer_repository_feature_map(
        files,
        chunks=chunks,
        source_root=repo_path,
        generated_at="2026-04-11T00:00:00+00:00",
    )
    return files, chunks, feature_map


def test_feature_memory_map_includes_feature_metadata(sample_repo_path):
    _files, chunks, feature_map = _build_feature_map(sample_repo_path)
    memory_map = build_memory_map(chunks, repository_feature_map=feature_map)
    assert memory_map["features"]
    assert memory_map["test_opportunities"]
    assert memory_map["schema_version"] == "2.0"


def test_feature_prompt_summary_mentions_feature_areas(sample_repo_path):
    _files, chunks, feature_map = _build_feature_map(sample_repo_path)
    prompt = format_memory_map_for_prompt(
        build_memory_map(chunks, repository_feature_map=feature_map)
    )
    assert "Feature areas" in prompt
    assert "Authentication" in prompt


def test_feature_summary_is_reviewable(sample_repo_path):
    _files, _chunks, feature_map = _build_feature_map(sample_repo_path)
    summary = format_feature_summary(feature_map)
    assert "Feature areas inferred" in summary
    assert "Todo Management" in summary


def test_saved_feature_memory_map_can_be_reloaded_for_reuse(sample_repo_path, tmp_path):
    _files, chunks, feature_map = _build_feature_map(sample_repo_path)
    memory_map = build_memory_map(chunks, repository_feature_map=feature_map)
    destination = tmp_path / "memory_map.json"

    save_memory_map(memory_map, str(destination))
    reloaded = load_memory_map(str(destination))
    prompt = format_memory_map_for_prompt(reloaded)

    assert reloaded["schema_version"] == "2.0"
    assert reloaded["features"]
    assert "Suggested test opportunities" in prompt
