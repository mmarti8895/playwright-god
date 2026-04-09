"""Unit tests for playwright_god.generator."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from playwright_god.embedder import MockEmbedder
from playwright_god.generator import (
    LLMClient,
    OpenAIClient,
    PlaywrightTestGenerator,
    TemplateLLMClient,
)
from playwright_god.indexer import RepositoryIndexer, SearchResult
from playwright_god.chunker import Chunk


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_search_result(
    file_path: str = "src/app.js",
    content: str = "const x = 1;",
    score: float = 0.9,
) -> SearchResult:
    chunk = Chunk(
        file_path=file_path,
        content=content,
        start_line=1,
        end_line=5,
        language="javascript",
        chunk_id="test_id",
    )
    return SearchResult(chunk=chunk, distance=1.0 - score, score=score)


def make_indexer_with_chunks(chunks_content: list[str]) -> RepositoryIndexer:
    indexer = RepositoryIndexer(
        collection_name="gen_test",
        persist_dir=None,
        embedder=MockEmbedder(),
    )
    from playwright_god.chunker import Chunk
    chunks = [
        Chunk(
            file_path=f"file{i}.js",
            content=text,
            start_line=1,
            end_line=5,
            language="javascript",
            chunk_id=Chunk._make_id(f"file{i}.js", 1, 5),
        )
        for i, text in enumerate(chunks_content)
    ]
    indexer.add_chunks(chunks)
    return indexer


# ---------------------------------------------------------------------------
# TemplateLLMClient
# ---------------------------------------------------------------------------


class TestTemplateLLMClient:
    def setup_method(self):
        self.client = TemplateLLMClient()

    def test_returns_string(self):
        result = self.client.complete("Description: test login")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_output_contains_playwright_import(self):
        result = self.client.complete("Description: user login")
        assert "@playwright/test" in result

    def test_output_contains_test_describe(self):
        result = self.client.complete("Description: login page")
        assert "test.describe" in result or "test(" in result

    def test_output_contains_page_goto(self):
        result = self.client.complete("Description: navigate to home page http://localhost:3000")
        assert "page.goto" in result

    def test_url_extracted_from_prompt(self):
        prompt = "Description: load app\nContext:\nhttp://localhost:8080/app"
        result = self.client.complete(prompt)
        assert "http://localhost:8080/app" in result

    def test_selectors_extracted(self):
        prompt = (
            "Description: login\n"
            'Context:\n<input id="email" />\n<input id="password" />\n'
        )
        result = self.client.complete(prompt)
        assert "email" in result or "password" in result

    def test_form_fields_extracted(self):
        prompt = (
            "Description: fill form\n"
            "Context:\n"
            '<label for="name">Name</label>\n'
            '<input type="text" placeholder="Your name" />\n'
        )
        result = self.client.complete(prompt)
        assert "Name" in result or "fill" in result

    def test_extract_description_from_prompt(self):
        desc = TemplateLLMClient._extract_description(
            "Description: user login flow\nContext: something"
        )
        assert desc == "user login flow"

    def test_extract_description_fallback(self):
        desc = TemplateLLMClient._extract_description("no description here")
        assert isinstance(desc, str)

    def test_extract_urls(self):
        urls = TemplateLLMClient._extract_urls(
            "navigate to https://example.com/page and http://localhost:3000"
        )
        assert "https://example.com/page" in urls
        assert "http://localhost:3000" in urls

    def test_extract_urls_empty(self):
        assert TemplateLLMClient._extract_urls("no urls here") == []

    def test_extract_selectors_by_id(self):
        sels = TemplateLLMClient._extract_selectors('getElementById("my-button")')
        assert "my-button" in sels

    def test_extract_selectors_data_testid(self):
        sels = TemplateLLMClient._extract_selectors('data-testid="submit-btn"')
        assert "submit-btn" in sels

    def test_extract_text_content_headings(self):
        texts = TemplateLLMClient._extract_text_content("<h1>Welcome</h1><h2>Login</h2>")
        assert "Welcome" in texts
        assert "Login" in texts

    def test_extract_text_content_buttons(self):
        texts = TemplateLLMClient._extract_text_content("<button>Submit</button>")
        assert "Submit" in texts

    def test_extract_form_fields(self):
        html = (
            '<label for="email">Email</label>'
            '<input type="email" placeholder="you@example.com" />'
        )
        pairs = TemplateLLMClient._extract_form_fields(html)
        assert len(pairs) == 1
        assert pairs[0][0] == "Email"
        assert pairs[0][1] == "you@example.com"

    def test_slugify(self):
        assert TemplateLLMClient._slugify("hello world!") == "hello world"
        assert TemplateLLMClient._slugify("foo-bar_baz") == "foo bar baz"


# ---------------------------------------------------------------------------
# PlaywrightTestGenerator
# ---------------------------------------------------------------------------


class TestPlaywrightTestGeneratorInit:
    def test_default_llm_is_template(self):
        gen = PlaywrightTestGenerator()
        assert isinstance(gen.llm_client, TemplateLLMClient)

    def test_custom_llm(self):
        mock_llm = MagicMock(spec=LLMClient)
        gen = PlaywrightTestGenerator(llm_client=mock_llm)
        assert gen.llm_client is mock_llm

    def test_no_indexer_by_default(self):
        gen = PlaywrightTestGenerator()
        assert gen.indexer is None


class TestPlaywrightTestGeneratorGenerate:
    def test_returns_string(self):
        gen = PlaywrightTestGenerator()
        result = gen.generate("test the login form")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_uses_llm_client(self):
        mock_llm = MagicMock(spec=LLMClient)
        mock_llm.complete.return_value = "// mock test"
        gen = PlaywrightTestGenerator(llm_client=mock_llm)
        result = gen.generate("test something")
        mock_llm.complete.assert_called_once()
        assert result == "// mock test"

    def test_generates_test_with_indexer(self):
        indexer = make_indexer_with_chunks(
            [
                "function login(user, pass) { ... }",
                "const loginUrl = '/login';",
            ]
        )
        gen = PlaywrightTestGenerator(indexer=indexer)
        result = gen.generate("login flow")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_description_appears_in_prompt(self):
        captured_prompts: list[str] = []

        class CapturingLLM(LLMClient):
            def complete(self, prompt: str) -> str:
                captured_prompts.append(prompt)
                return "// result"

        gen = PlaywrightTestGenerator(llm_client=CapturingLLM())
        gen.generate("the unique description XYZ")
        assert captured_prompts
        assert "the unique description XYZ" in captured_prompts[0]

    def test_extra_context_in_prompt(self):
        captured: list[str] = []

        class CapturingLLM(LLMClient):
            def complete(self, prompt: str) -> str:
                captured.append(prompt)
                return ""

        gen = PlaywrightTestGenerator(llm_client=CapturingLLM())
        gen.generate("desc", extra_context="EXTRA_CONTEXT_MARKER")
        assert "EXTRA_CONTEXT_MARKER" in captured[0]

    def test_context_chunks_in_prompt(self):
        captured: list[str] = []

        class CapturingLLM(LLMClient):
            def complete(self, prompt: str) -> str:
                captured.append(prompt)
                return ""

        indexer = make_indexer_with_chunks(["UNIQUE_CHUNK_CONTENT"])
        gen = PlaywrightTestGenerator(llm_client=CapturingLLM(), indexer=indexer)
        gen.generate("test something")
        assert "UNIQUE_CHUNK_CONTENT" in captured[0]


class TestBuildPrompt:
    def test_prompt_contains_description(self):
        gen = PlaywrightTestGenerator()
        prompt = gen._build_prompt("my desc", [], None)
        assert "my desc" in prompt

    def test_prompt_contains_context(self):
        gen = PlaywrightTestGenerator()
        result = make_search_result(content="LOGIN_CODE_HERE")
        prompt = gen._build_prompt("desc", [result], None)
        assert "LOGIN_CODE_HERE" in prompt

    def test_prompt_without_context(self):
        gen = PlaywrightTestGenerator()
        prompt = gen._build_prompt("desc", [], None)
        assert "desc" in prompt

    def test_prompt_with_extra_context(self):
        gen = PlaywrightTestGenerator()
        prompt = gen._build_prompt("desc", [], "EXTRA")
        assert "EXTRA" in prompt
