"""Shared test configuration and fixtures."""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "requires_node: skip unless `npx` and `@playwright/test` are available locally",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    skip_node = pytest.mark.skip(reason="npx not available; install Node 18+")
    has_npx = shutil.which("npx") is not None
    for item in items:
        if "requires_node" in item.keywords and not has_npx:
            item.add_marker(skip_node)

from playwright_god.crawler import FileInfo
from playwright_god.crawler import RepositoryCrawler
from playwright_god.chunker import Chunk
from playwright_god.embedder import MockEmbedder
from playwright_god.indexer import RepositoryIndexer

# Path to the small sample app used in tests
FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_APP_DIR = FIXTURES_DIR / "sample_app"


@pytest.fixture()
def sample_repo_path() -> str:
    """Return the path to the sample app fixture directory."""
    return str(SAMPLE_APP_DIR)


@pytest.fixture()
def sample_repo_files(sample_repo_path: str) -> list[FileInfo]:
    """Return all crawlable files from the sample repository fixture."""
    return RepositoryCrawler().crawl(sample_repo_path)


@pytest.fixture()
def simple_file_info() -> FileInfo:
    """A minimal FileInfo fixture."""
    content = "function hello() {\n  console.log('hello');\n}\n"
    return FileInfo(
        path="src/hello.js",
        absolute_path="/repo/src/hello.js",
        content=content,
        language="javascript",
        size=len(content.encode()),
    )


@pytest.fixture()
def simple_chunk(simple_file_info: FileInfo) -> Chunk:
    """A minimal Chunk fixture."""
    return Chunk(
        file_path=simple_file_info.path,
        content=simple_file_info.content,
        start_line=1,
        end_line=3,
        language=simple_file_info.language,
        chunk_id="abc123",
    )


@pytest.fixture()
def sample_event_payload() -> dict:
    """A minimal event payload for E2E tests."""
    return {"title": "Test Event", "description": "A test description", "date": "2026-01-01"}


@pytest.fixture()
def in_memory_indexer() -> RepositoryIndexer:
    """Return an in-memory RepositoryIndexer using the MockEmbedder.

    Each test gets its own collection via a unique name so ChromaDB's
    ephemeral client does not leak state between tests.
    """
    unique_name = f"test_{uuid.uuid4().hex}"
    return RepositoryIndexer(
        collection_name=unique_name,
        persist_dir=None,          # ephemeral (in-memory)
        embedder=MockEmbedder(),
    )
