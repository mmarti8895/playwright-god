"""Integration tests: full pipeline from crawl → index → generate."""

from __future__ import annotations

import uuid

import pytest

from playwright_god.crawler import RepositoryCrawler
from playwright_god.chunker import FileChunker
from playwright_god.embedder import MockEmbedder
from playwright_god.generator import PlaywrightTestGenerator, TemplateLLMClient
from playwright_god.indexer import RepositoryIndexer


def _unique_indexer() -> RepositoryIndexer:
    """Create a fresh in-memory indexer with a unique collection name."""
    return RepositoryIndexer(
        collection_name=f"integ_{uuid.uuid4().hex}",
        persist_dir=None,
        embedder=MockEmbedder(),
    )


class TestFullPipeline:
    """End-to-end test of the complete RAG pipeline."""

    def _build_indexer(self, repo_path: str) -> RepositoryIndexer:
        """Run crawl → chunk → index and return the populated indexer."""
        crawler = RepositoryCrawler()
        files = crawler.crawl(repo_path)
        assert files, "Sample app must contain crawlable files"

        chunker = FileChunker(chunk_size=30, overlap=5)
        chunks = chunker.chunk_files(files)
        assert chunks, "Chunker must produce at least one chunk"

        indexer = _unique_indexer()
        indexer.add_chunks(chunks)
        return indexer

    def test_crawl_produces_files(self, sample_repo_path):
        crawler = RepositoryCrawler()
        files = crawler.crawl(sample_repo_path)
        file_names = [f.path for f in files]
        assert any("index.html" in p for p in file_names)
        assert any("app.js" in p for p in file_names)

    def test_full_pipeline_indexes_chunks(self, sample_repo_path):
        indexer = self._build_indexer(sample_repo_path)
        assert indexer.count() > 0

    def test_search_returns_relevant_result(self, sample_repo_path):
        indexer = self._build_indexer(sample_repo_path)
        results = indexer.search("login form", n_results=3)
        assert len(results) > 0
        # At least one result should come from a file we know about
        file_paths = {r.chunk.file_path for r in results}
        assert file_paths  # non-empty

    def test_generate_without_llm(self, sample_repo_path):
        """TemplateLLMClient generates a test without any API call."""
        indexer = self._build_indexer(sample_repo_path)
        generator = PlaywrightTestGenerator(
            llm_client=TemplateLLMClient(),
            indexer=indexer,
        )
        test_code = generator.generate("login form with email and password")
        assert isinstance(test_code, str)
        assert "@playwright/test" in test_code
        assert "page.goto" in test_code

    def test_generate_includes_context_from_html(self, sample_repo_path):
        """Context chunks from the HTML file should influence generation."""
        indexer = self._build_indexer(sample_repo_path)

        captured: list[str] = []

        class CapturingLLM:
            def complete(self, prompt: str) -> str:
                captured.append(prompt)
                return "// captured"

        gen = PlaywrightTestGenerator(
            llm_client=CapturingLLM(),
            indexer=indexer,
            n_context=10,
        )
        gen.generate("login form")
        assert captured
        prompt = captured[0]
        # The HTML form context should be included
        assert "login" in prompt.lower() or "email" in prompt.lower()

    def test_structure_summary_readable(self, sample_repo_path):
        crawler = RepositoryCrawler()
        files = crawler.crawl(sample_repo_path)
        summary = crawler.build_structure_summary(files)
        assert isinstance(summary, str)
        assert len(summary) > 0
        # Summary should mention the languages present
        assert "html" in summary or "javascript" in summary

    def test_pipeline_idempotent_add(self, sample_repo_path):
        """Adding the same chunks twice should not duplicate index entries."""
        crawler = RepositoryCrawler()
        files = crawler.crawl(sample_repo_path)
        chunker = FileChunker(chunk_size=30, overlap=5)
        chunks = chunker.chunk_files(files)

        indexer = _unique_indexer()
        indexer.add_chunks(chunks)
        count_after_first = indexer.count()
        indexer.add_chunks(chunks)  # second add – should upsert
        assert indexer.count() == count_after_first

    def test_generate_with_custom_mock_llm(self, sample_repo_path):
        from unittest.mock import MagicMock
        from playwright_god.generator import LLMClient

        mock_llm = MagicMock(spec=LLMClient)
        mock_llm.complete.return_value = "test('example', async ({ page }) => {});"

        indexer = self._build_indexer(sample_repo_path)
        gen = PlaywrightTestGenerator(llm_client=mock_llm, indexer=indexer)
        result = gen.generate("todo list CRUD operations")

        mock_llm.complete.assert_called_once()
        assert result == "test('example', async ({ page }) => {});"
