"""Integration tests for the logging-aware RAG pipeline.

Covers log assertion generation end-to-end:
crawl → index → generate with auth_type="logging" (or log keywords in description)
→ assert output contains console/pageerror/route patterns.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from playwright_god.chunker import FileChunker
from playwright_god.crawler import RepositoryCrawler
from playwright_god.embedder import MockEmbedder
from playwright_god.generator import PlaywrightTestGenerator, TemplateLLMClient
from playwright_god.indexer import RepositoryIndexer

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
LOGGING_APP_DIR = FIXTURES_DIR / "logging_app"


def _unique_indexer() -> RepositoryIndexer:
    return RepositoryIndexer(
        collection_name=f"log_integ_{uuid.uuid4().hex}",
        persist_dir=None,
        embedder=MockEmbedder(),
    )


def _build_indexer(repo_path: str) -> RepositoryIndexer:
    crawler = RepositoryCrawler()
    files = crawler.crawl(repo_path)
    assert files, "Logging app fixture must contain crawlable files"
    chunker = FileChunker(chunk_size=30, overlap=5)
    chunks = chunker.chunk_files(files)
    indexer = _unique_indexer()
    indexer.add_chunks(chunks)
    return indexer


# ---------------------------------------------------------------------------
# Crawler: logging config files
# ---------------------------------------------------------------------------


class TestCrawlerLoggingFiles:
    def test_logging_app_crawled(self):
        crawler = RepositoryCrawler()
        files = crawler.crawl(str(LOGGING_APP_DIR))
        assert files

    def test_winston_config_not_skipped(self):
        """winston.config.js must be indexed."""
        crawler = RepositoryCrawler()
        files = crawler.crawl(str(LOGGING_APP_DIR))
        file_names = [f.path for f in files]
        assert any("winston.config.js" in p for p in file_names)

    def test_winston_config_language_is_javascript(self):
        crawler = RepositoryCrawler()
        files = crawler.crawl(str(LOGGING_APP_DIR))
        for f in files:
            if "winston.config.js" in f.path:
                assert f.language == "javascript"
                break

    def test_logging_html_crawled(self):
        crawler = RepositoryCrawler()
        files = crawler.crawl(str(LOGGING_APP_DIR))
        file_names = [f.path for f in files]
        assert any("index.html" in p for p in file_names)


# ---------------------------------------------------------------------------
# TemplateLLMClient: log keyword detection
# ---------------------------------------------------------------------------


class TestTemplateLLMClientLogging:
    def setup_method(self):
        self.client = TemplateLLMClient()

    def _generate(self, description: str) -> str:
        prompt = f"Description: {description}\nContext:\nhttp://localhost:3000"
        return self.client.complete(prompt)

    def test_logging_keyword_triggers_log_tests(self):
        code = self._generate("audit logging for delete action")
        assert 'page.on("console"' in code or "page.on(" in code

    def test_audit_trail_keyword_triggers_log_tests(self):
        code = self._generate("audit trail validation")
        assert 'page.on("console"' in code or "pageerror" in code.lower()

    def test_error_log_keyword_triggers_log_tests(self):
        code = self._generate("error log capture on form submit")
        assert "pageerror" in code.lower() or "errors" in code

    def test_console_output_keyword_triggers_log_tests(self):
        code = self._generate("console output verification")
        assert "console" in code

    def test_page_route_intercept_in_log_tests(self):
        code = self._generate("audit logging for API calls")
        assert "page.route(" in code or "route(" in code

    def test_no_log_tests_for_plain_description(self):
        code = self._generate("user fills in the registration form")
        # Should not inject log tests for an unrelated description
        assert 'page.on("pageerror"' not in code

    def test_log_tests_have_no_uncaught_errors_block(self):
        code = self._generate("logging and audit")
        assert "uncaught" in code.lower() or "pageerror" in code.lower()

    def test_is_logging_description_true_for_logging(self):
        assert TemplateLLMClient._is_logging_description("audit logging")

    def test_is_logging_description_true_for_splunk(self):
        assert TemplateLLMClient._is_logging_description("send events to splunk")

    def test_is_logging_description_false_for_unrelated(self):
        assert not TemplateLLMClient._is_logging_description("user registration form")


# ---------------------------------------------------------------------------
# Generator.generate with auth_type="logging"
# ---------------------------------------------------------------------------


class TestGenerateLoggingAuthType:
    def test_logging_auth_type_injects_hint(self):
        captured: list[str] = []

        class CapturingLLM:
            def complete(self, prompt: str) -> str:
                captured.append(prompt)
                return "// captured"

        gen = PlaywrightTestGenerator(llm_client=CapturingLLM())
        gen.generate("application event logging", auth_type="logging")
        assert captured
        assert "console" in captured[0]

    def test_logging_auth_type_injects_template(self):
        captured: list[str] = []

        class CapturingLLM:
            def complete(self, prompt: str) -> str:
                captured.append(prompt)
                return "// captured"

        gen = PlaywrightTestGenerator(llm_client=CapturingLLM())
        gen.generate("log assertions", auth_type="logging")
        prompt = captured[0]
        assert 'page.on("console"' in prompt
        assert 'page.on("pageerror"' in prompt
        assert "page.route(" in prompt


# ---------------------------------------------------------------------------
# Full pipeline: logging app crawl → generate
# ---------------------------------------------------------------------------


class TestLoggingPipeline:
    def test_full_logging_pipeline_template_client(self):
        """End-to-end: index logging app, generate with logging keyword."""
        indexer = _build_indexer(str(LOGGING_APP_DIR))
        generator = PlaywrightTestGenerator(
            llm_client=TemplateLLMClient(),
            indexer=indexer,
        )
        test_code = generator.generate("audit logging for delete action")
        assert isinstance(test_code, str)
        assert 'import { test, expect } from "@playwright/test";' in test_code
        assert "page.goto" in test_code

    def test_logging_pipeline_with_auth_type(self):
        """generate() with auth_type='logging' injects the template into the prompt."""
        captured: list[str] = []

        class CapturingLLM:
            def complete(self, prompt: str) -> str:
                captured.append(prompt)
                return "// captured"

        indexer = _build_indexer(str(LOGGING_APP_DIR))
        gen = PlaywrightTestGenerator(llm_client=CapturingLLM(), indexer=indexer)
        gen.generate("console log and audit trail", auth_type="logging")

        assert captured
        prompt = captured[0]
        # Both the RAG context and the logging template should appear
        assert "console" in prompt
        assert "page.on" in prompt or "pageerror" in prompt

    def test_logging_pipeline_context_includes_winston_config(self):
        """The winston.config.js should contribute to the retrieved context."""
        captured: list[str] = []

        class CapturingLLM:
            def complete(self, prompt: str) -> str:
                captured.append(prompt)
                return "// captured"

        indexer = _build_indexer(str(LOGGING_APP_DIR))
        gen = PlaywrightTestGenerator(
            llm_client=CapturingLLM(), indexer=indexer, n_context=20
        )
        gen.generate("winston logging configuration")
        assert captured
        # winston.config.js content should appear in the RAG context
        assert "winston" in captured[0].lower()
