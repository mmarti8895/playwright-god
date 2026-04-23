"""Unit tests for playwright_god.generator."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from playwright_god.embedder import MockEmbedder
from playwright_god.generator import (
    AnthropicClient,
    GeminiClient,
    LLMClient,
    OllamaClient,
    OpenAIClient,
    PlaywrightCLIClient,
    PlaywrightCLIError,
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
        assert 'import { test, expect } from "@playwright/test";' in result

    def test_output_contains_typescript_test_block(self):
        result = self.client.complete("Description: login page")
        assert 'test("' in result

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

    def test_text_content_is_rendered_as_visible_assertions(self):
        prompt = 'Description: landing page\nContext:\n<h1>Welcome "Home"</h1>'
        result = self.client.complete(prompt)
        assert 'await expect(page.getByText("Welcome \\"Home\\"")).toBeVisible();' in result

    def test_logging_description_adds_route_observer(self):
        result = self.client.complete("Description: audit logging for delete action")
        assert 'await page.route("**/*", async (route) => {' in result
        assert 'page.on("pageerror"' in result

    def test_plan_detection_does_not_trigger_from_context_only(self):
        prompt = (
            "Description: test login flow\n\n"
            "Context (relevant repository code):\n"
            "some helper text mentioning Generate a Markdown test plan inside a source file\n\n"
            "============================================================\n"
            "Write a comprehensive TypeScript Playwright test suite for the description above."
        )
        result = self.client.complete(prompt)
        assert 'import { test, expect } from "@playwright/test";' in result

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

    def test_test_name_uses_fallback_when_slug_is_empty(self):
        assert TemplateLLMClient._test_name("!!!", "fallback_name") == "test_fallback_name"

    def test_generate_plan_without_file_paths_uses_generic_scenarios(self):
        result = self.client.complete("Generate a Markdown test plan")
        assert "Home page loads and key elements are visible" in result


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
        mock_llm.complete.return_value = "# mock test"
        gen = PlaywrightTestGenerator(llm_client=mock_llm)
        result = gen.generate("test something")
        mock_llm.complete.assert_called_once()
        assert result == "# mock test"

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
            def complete(self, prompt: str, system_prompt: str | None = None) -> str:
                captured_prompts.append(prompt)
                return "# result"

        gen = PlaywrightTestGenerator(llm_client=CapturingLLM())
        gen.generate("the unique description XYZ")
        assert captured_prompts
        assert "the unique description XYZ" in captured_prompts[0]

    def test_extra_context_in_prompt(self):
        captured: list[str] = []

        class CapturingLLM(LLMClient):
            def complete(self, prompt: str, system_prompt: str | None = None) -> str:
                captured.append(prompt)
                return ""

        gen = PlaywrightTestGenerator(llm_client=CapturingLLM())
        gen.generate("desc", extra_context="EXTRA_CONTEXT_MARKER")
        assert "EXTRA_CONTEXT_MARKER" in captured[0]

    def test_context_chunks_in_prompt(self):
        captured: list[str] = []

        class CapturingLLM(LLMClient):
            def complete(self, prompt: str, system_prompt: str | None = None) -> str:
                captured.append(prompt)
                return ""

        indexer = make_indexer_with_chunks(["UNIQUE_CHUNK_CONTENT"])
        gen = PlaywrightTestGenerator(llm_client=CapturingLLM(), indexer=indexer)
        gen.generate("test something")
        assert "UNIQUE_CHUNK_CONTENT" in captured[0]

    def test_auth_hint_and_extra_context_are_combined(self):
        captured: list[str] = []

        class CapturingLLM(LLMClient):
            def complete(self, prompt: str, system_prompt: str | None = None) -> str:
                captured.append(prompt)
                return ""

        gen = PlaywrightTestGenerator(llm_client=CapturingLLM())
        gen.generate("login flow", auth_type="saml", extra_context="CUSTOM_EXTRA")
        assert "Reference TypeScript template" in captured[0]
        assert "CUSTOM_EXTRA" in captured[0]

    def test_auth_hint_without_extra_context_is_included(self):
        captured: list[str] = []

        class CapturingLLM(LLMClient):
            def complete(self, prompt: str, system_prompt: str | None = None) -> str:
                captured.append(prompt)
                return ""

        gen = PlaywrightTestGenerator(llm_client=CapturingLLM())
        gen.generate("log capture", auth_type="logging")
        assert "Logging or audit testing." in captured[0]

    def test_generation_mode_block_is_included(self):
        captured: list[str] = []

        class CapturingLLM(LLMClient):
            def complete(self, prompt: str, system_prompt: str | None = None) -> str:
                captured.append(prompt)
                return "// ok"

        gen = PlaywrightTestGenerator(llm_client=CapturingLLM())
        gen.generate("login flow", generation_mode="hybrid")
        assert "Generation mode" in captured[0]
        assert "Mode: hybrid" in captured[0]

    def test_generated_output_includes_provenance_banner(self):
        class StaticLLM(LLMClient):
            def complete(self, prompt: str, system_prompt: str | None = None) -> str:
                return 'import { test, expect } from "@playwright/test";'

        gen = PlaywrightTestGenerator(llm_client=StaticLLM())
        result = gen.generate("login flow", generation_mode="gap-fill")
        assert result.startswith("// Generated by playwright-god (mode=gap-fill")


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


class TestSecretRedaction:
    def test_redaction_uses_process_env_placeholders(self):
        code = PlaywrightTestGenerator._redact_secrets('password = "plain-secret"')
        assert 'process.env.TEST_PASSWORD ?? ""' in code

    def test_safe_values_are_not_replaced(self):
        original = 'password = "CHANGE_ME"'
        assert PlaywrightTestGenerator._redact_secrets(original) == original


# ---------------------------------------------------------------------------
# OpenAIClient
# ---------------------------------------------------------------------------


class TestOpenAIClient:
    def test_raises_without_openai_package(self):
        with patch.dict("sys.modules", {"openai": None}):
            with pytest.raises(ImportError, match="openai"):
                OpenAIClient(api_key="test")

    def test_complete_calls_api(self):
        mock_openai = MagicMock()
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "// generated test"
        mock_openai.OpenAI.return_value.chat.completions.create.return_value = mock_response

        with patch.dict("sys.modules", {"openai": mock_openai}):
            client = OpenAIClient(api_key="test-key", model="gpt-4o")
            result = client.complete("some prompt")

        assert result == "// generated test"
        mock_openai.OpenAI.return_value.chat.completions.create.assert_called_once()

    def test_complete_retries_transient_connection_error(self):
        mock_openai = MagicMock()
        retry_error = type("APIConnectionError", (Exception,), {})
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "// generated after retry"
        mock_openai.OpenAI.return_value.chat.completions.create.side_effect = [
            retry_error("Connection error."),
            mock_response,
        ]

        with (
            patch.dict("sys.modules", {"openai": mock_openai}),
            patch("playwright_god.generator.time.sleep") as mock_sleep,
        ):
            client = OpenAIClient(api_key="test-key", model="gpt-4o")
            result = client.complete("some prompt")

        assert result == "// generated after retry"
        assert mock_openai.OpenAI.return_value.chat.completions.create.call_count == 2
        mock_sleep.assert_called_once_with(0.5)

    def test_complete_raises_after_retry_budget_exhausted(self):
        mock_openai = MagicMock()
        retry_error = type("APIConnectionError", (Exception,), {})
        mock_openai.OpenAI.return_value.chat.completions.create.side_effect = [
            retry_error("Connection error."),
            retry_error("Connection error."),
        ]

        with (
            patch.dict("sys.modules", {"openai": mock_openai}),
            patch("playwright_god.generator.time.sleep") as mock_sleep,
        ):
            client = OpenAIClient(api_key="test-key", model="gpt-4o")
            with pytest.raises(retry_error, match="Connection error."):
                client.complete("some prompt")

        assert mock_openai.OpenAI.return_value.chat.completions.create.call_count == 2
        mock_sleep.assert_called_once_with(0.5)


# ---------------------------------------------------------------------------
# AnthropicClient
# ---------------------------------------------------------------------------


class TestAnthropicClient:
    def test_raises_without_anthropic_package(self):
        with patch.dict("sys.modules", {"anthropic": None}):
            with pytest.raises(ImportError, match="anthropic"):
                AnthropicClient(api_key="test")

    def test_complete_calls_api(self):
        mock_anthropic = MagicMock()
        mock_response = MagicMock()
        mock_response.content[0].text = "// anthropic generated test"
        mock_anthropic.Anthropic.return_value.messages.create.return_value = mock_response

        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            client = AnthropicClient(api_key="test-key", model="claude-3-7-sonnet-latest")
            result = client.complete("some prompt")

        assert result == "// anthropic generated test"
        mock_anthropic.Anthropic.return_value.messages.create.assert_called_once()

    def test_complete_passes_system_prompt(self):
        mock_anthropic = MagicMock()
        mock_response = MagicMock()
        mock_response.content[0].text = "result"
        mock_anthropic.Anthropic.return_value.messages.create.return_value = mock_response

        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            client = AnthropicClient(api_key="test-key")
            client.complete("test prompt")

        call_kwargs = mock_anthropic.Anthropic.return_value.messages.create.call_args[1]
        assert call_kwargs["system"] == PlaywrightTestGenerator.SYSTEM_PROMPT

    def test_default_model(self):
        mock_anthropic = MagicMock()
        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            client = AnthropicClient(api_key="test-key")
        assert client.model == "claude-3-7-sonnet-latest"


# ---------------------------------------------------------------------------
# GeminiClient
# ---------------------------------------------------------------------------


class TestGeminiClient:
    def test_raises_without_google_generativeai_package(self):
        with patch.dict("sys.modules", {"google.generativeai": None, "google": None}):
            with pytest.raises(ImportError, match="google-generativeai"):
                GeminiClient(api_key="test")

    def test_complete_calls_api(self):
        mock_genai = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "// gemini generated test"
        mock_genai.GenerativeModel.return_value.generate_content.return_value = mock_response

        mock_google = MagicMock()
        mock_google.generativeai = mock_genai

        with patch.dict("sys.modules", {"google": mock_google, "google.generativeai": mock_genai}):
            client = GeminiClient(api_key="test-key", model="gemini-1.5-pro")
            result = client.complete("some prompt")

        assert result == "// gemini generated test"
        mock_genai.GenerativeModel.return_value.generate_content.assert_called_once_with(
            "some prompt"
        )

    def test_default_model(self):
        mock_genai = MagicMock()
        mock_google = MagicMock()
        mock_google.generativeai = mock_genai

        with patch.dict("sys.modules", {"google": mock_google, "google.generativeai": mock_genai}):
            client = GeminiClient(api_key="test-key")

        mock_genai.GenerativeModel.assert_called_once()
        call_kwargs = mock_genai.GenerativeModel.call_args
        assert call_kwargs[1]["model_name"] == "gemini-1.5-pro"

    def test_complete_uses_cached_model_for_custom_system_prompt(self):
        mock_genai = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "custom"
        mock_genai.GenerativeModel.return_value.generate_content.return_value = mock_response
        mock_google = MagicMock()
        mock_google.generativeai = mock_genai

        with patch.dict("sys.modules", {"google": mock_google, "google.generativeai": mock_genai}):
            client = GeminiClient(api_key="test-key")
            result = client.complete("some prompt", system_prompt="CUSTOM SYSTEM")

        assert result == "custom"
        assert mock_genai.GenerativeModel.call_count == 2


# ---------------------------------------------------------------------------
# OllamaClient
# ---------------------------------------------------------------------------


class TestOllamaClient:
    def test_raises_without_requests_package(self):
        with patch.dict("sys.modules", {"requests": None}):
            with pytest.raises(ImportError, match="requests"):
                OllamaClient()

    def test_default_model_and_url(self):
        client = OllamaClient()
        assert client.model == "llama3"
        assert client.base_url == "http://localhost:11434"

    def test_custom_model_and_url(self):
        client = OllamaClient(model="mistral", base_url="http://myserver:11434")
        assert client.model == "mistral"
        assert client.base_url == "http://myserver:11434"

    def test_trailing_slash_stripped_from_url(self):
        client = OllamaClient(base_url="http://localhost:11434/")
        assert client.base_url == "http://localhost:11434"

    def test_complete_calls_rest_api(self):
        mock_requests = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"message": {"content": "// ollama result"}}
        mock_response.raise_for_status = MagicMock()
        mock_requests.post.return_value = mock_response

        with patch.dict("sys.modules", {"requests": mock_requests}):
            client = OllamaClient(model="llama3")
            result = client.complete("some prompt")

        assert result == "// ollama result"
        mock_requests.post.assert_called_once()
        call_args = mock_requests.post.call_args
        assert call_args[0][0] == "http://localhost:11434/api/chat"
        payload = call_args[1]["json"]
        assert payload["model"] == "llama3"
        assert payload["stream"] is False

    def test_complete_passes_system_and_user_messages(self):
        mock_requests = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"message": {"content": "result"}}
        mock_response.raise_for_status = MagicMock()
        mock_requests.post.return_value = mock_response

        with patch.dict("sys.modules", {"requests": mock_requests}):
            client = OllamaClient()
            client.complete("user message")

        payload = mock_requests.post.call_args[1]["json"]
        roles = [m["role"] for m in payload["messages"]]
        assert roles == ["system", "user"]
        assert payload["messages"][1]["content"] == "user message"


# ---------------------------------------------------------------------------
# Coverage-aware prompt injection (coverage-aware-planning)
# ---------------------------------------------------------------------------


class _RecordingClient:
    def __init__(self):
        self.last_prompt = None

    def complete(self, prompt, system_prompt=None):
        self.last_prompt = prompt
        return "// generated"


class TestUncoveredExcerptInjection:
    def test_block_appended_when_excerpts_provided(self):
        from playwright_god.generator import PlaywrightTestGenerator

        client = _RecordingClient()
        gen = PlaywrightTestGenerator(llm_client=client)
        excerpts = [("src/a.ts", 1, 3, "alpha\nbeta\ngamma")]
        gen.generate("login flow", uncovered_excerpts=excerpts)
        assert "Uncovered code (gaps)" in client.last_prompt
        assert "src/a.ts" in client.last_prompt
        assert "alpha" in client.last_prompt

    def test_cap_truncates_excerpts(self):
        from playwright_god.generator import PlaywrightTestGenerator

        client = _RecordingClient()
        gen = PlaywrightTestGenerator(llm_client=client)
        excerpts = [(f"f{i}.ts", 1, 1, f"body{i}") for i in range(20)]
        gen.generate("scenario", uncovered_excerpts=excerpts, uncovered_cap=5)
        prompt = client.last_prompt
        # Only first 5 should appear; the rest are noted as omitted.
        for i in range(5):
            assert f"f{i}.ts" in prompt
        for i in range(5, 20):
            assert f"f{i}.ts" not in prompt
        assert "+15 more" in prompt

    def test_no_block_when_excerpts_empty(self):
        from playwright_god.generator import PlaywrightTestGenerator

        client = _RecordingClient()
        gen = PlaywrightTestGenerator(llm_client=client)
        gen.generate("x", uncovered_excerpts=[])
        assert "Uncovered code (gaps)" not in client.last_prompt


class TestCoverageDeltaInPlan:
    def test_plan_includes_coverage_delta_section(self):
        from playwright_god.generator import PlaywrightTestGenerator

        client = _RecordingClient()
        gen = PlaywrightTestGenerator(llm_client=client)
        coverage = {
            "summary": {"files": 2, "covered_lines": 5, "uncovered_lines": 5,
                        "percent": 50.0},
            "files": [
                {"path": "a.ts", "covered_lines": [1], "uncovered_lines": [2, 3, 4],
                 "percent": 25.0},
                {"path": "b.py", "covered_lines": [1, 2], "uncovered_lines": [3, 4],
                 "percent": 50.0},
            ],
        }
        gen.plan("memory map", coverage=coverage)
        assert "## Coverage Delta" in client.last_prompt
        # Default prioritisation = absolute (most uncovered first) so a.ts wins.
        idx_a = client.last_prompt.find("`a.ts`")
        idx_b = client.last_prompt.find("`b.py`")
        assert 0 < idx_a < idx_b

    def test_plan_prioritise_percent_orders_lowest_first(self):
        from playwright_god.generator import PlaywrightTestGenerator

        client = _RecordingClient()
        gen = PlaywrightTestGenerator(llm_client=client)
        coverage = {
            "summary": {},
            "files": [
                {"path": "a.ts", "uncovered_lines": [1, 2, 3, 4, 5], "percent": 90.0},
                {"path": "b.py", "uncovered_lines": [1], "percent": 10.0},
            ],
        }
        gen.plan("mm", coverage=coverage, prioritize="percent")
        idx_a = client.last_prompt.find("`a.ts`")
        idx_b = client.last_prompt.find("`b.py`")
        assert 0 < idx_b < idx_a


class TestCoverageDeltaEdgeCases:
    def test_empty_files_returns_empty(self):
        from playwright_god.generator import PlaywrightTestGenerator
        assert PlaywrightTestGenerator._format_coverage_delta({"files": []}) == ""

    def test_all_files_fully_covered_returns_empty(self):
        from playwright_god.generator import PlaywrightTestGenerator
        out = PlaywrightTestGenerator._format_coverage_delta(
            {"files": [{"path": "a", "uncovered_lines": [], "percent": 100.0}]}
        )
        assert out == ""

    def test_format_uncovered_block_empty(self):
        from playwright_god.generator import PlaywrightTestGenerator
        assert PlaywrightTestGenerator._format_uncovered_block([]) == ""

    def test_format_uncovered_block_cap_zero(self):
        from playwright_god.generator import PlaywrightTestGenerator
        assert PlaywrightTestGenerator._format_uncovered_block(
            [("a", 1, 1, "x")], cap=0
        ) == ""


# ---------------------------------------------------------------------------
# iterative-refinement: addenda + byte-identity (Tasks 2.4 / 5.5)
# ---------------------------------------------------------------------------


class _PromptRecorder:
    """LLM client that records the last prompt it was sent."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete(self, prompt: str, system_prompt: str | None = None) -> str:  # noqa: ARG002
        self.prompts.append(prompt)
        return "// stub spec\n"


def test_generate_no_addenda_is_byte_identical() -> None:
    """The no-addenda call SHALL produce the same prompt as before this change."""
    from playwright_god.generator import PlaywrightTestGenerator

    client_a = _PromptRecorder()
    client_b = _PromptRecorder()
    PlaywrightTestGenerator(llm_client=client_a).generate("login flow")
    PlaywrightTestGenerator(llm_client=client_b).generate(
        "login flow",
        failure_excerpt=None,
        coverage_delta=None,
    )
    assert client_a.prompts == client_b.prompts


def test_generate_failure_excerpt_appends_section() -> None:
    from playwright_god.generator import PlaywrightTestGenerator

    client = _PromptRecorder()
    PlaywrightTestGenerator(llm_client=client).generate(
        "login flow",
        failure_excerpt="TypeError at app.ts:42",
    )
    assert "Previous attempt failure:" in client.prompts[0]
    assert "TypeError at app.ts:42" in client.prompts[0]


def test_generate_coverage_delta_appends_section() -> None:
    from playwright_god.generator import PlaywrightTestGenerator

    client = _PromptRecorder()
    delta = {
        "newly_covered": ["src/a.py"],
        "still_uncovered": ["src/b.py", "src/c.py"],
    }
    PlaywrightTestGenerator(llm_client=client).generate(
        "login flow",
        coverage_delta=delta,
    )
    p = client.prompts[0]
    assert "Coverage delta since last attempt:" in p
    assert "newly covered" in p.lower() or "+ src/a.py" in p
    assert "src/b.py" in p


def test_generate_empty_coverage_delta_emits_no_section() -> None:
    from playwright_god.generator import PlaywrightTestGenerator

    client = _PromptRecorder()
    PlaywrightTestGenerator(llm_client=client).generate(
        "login",
        coverage_delta={"newly_covered": [], "still_uncovered": []},
    )
    assert "Coverage delta since last attempt:" not in client.prompts[0]


def test_generate_failure_excerpt_truncated_at_2kb() -> None:
    from playwright_god.generator import PlaywrightTestGenerator

    client = _PromptRecorder()
    big = "X" * 5000
    PlaywrightTestGenerator(llm_client=client).generate(
        "login", failure_excerpt=big
    )
    p = client.prompts[0]
    assert "(truncated)" in p
    # The excerpt body should not exceed ~2KB inside the prompt.
    body = p.split("Previous attempt failure:", 1)[1]
    assert len(body.encode("utf-8")) < 2500


def test_generate_blank_failure_excerpt_ignored() -> None:
    from playwright_god.generator import PlaywrightTestGenerator

    client_a = _PromptRecorder()
    client_b = _PromptRecorder()
    PlaywrightTestGenerator(llm_client=client_a).generate("login")
    PlaywrightTestGenerator(llm_client=client_b).generate("login", failure_excerpt="   \n  ")
    assert client_a.prompts == client_b.prompts


def test_generate_coverage_delta_with_dataclass_object() -> None:
    """Accept any object exposing newly_covered / still_uncovered attributes."""
    from playwright_god.generator import PlaywrightTestGenerator
    from playwright_god.refinement import CoverageDelta

    client = _PromptRecorder()
    delta = CoverageDelta(
        newly_covered=("src/a.py",), still_uncovered=("src/b.py",), coverage_gain=0.1
    )
    PlaywrightTestGenerator(llm_client=client).generate(
        "login", coverage_delta=delta
    )
    assert "src/a.py" in client.prompts[0]
    assert "src/b.py" in client.prompts[0]


# ---------------------------------------------------------------------------
# Flow-graph integration (flow-graph-extraction)
# ---------------------------------------------------------------------------


def _flow_graph_with_routes_and_actions():
    from playwright_god.flow_graph import (
        Action,
        Evidence,
        FlowGraph,
        Route,
    )

    return FlowGraph.from_iterables(
        nodes=[
            Route(
                method="GET",
                path="/login",
                handler="login_handler",
                evidence=(Evidence("api/auth.py", (1, 5)),),
            ),
            Route(
                method="POST",
                path="/items",
                handler="create_item",
                evidence=(Evidence("api/items.py", (10, 20)),),
            ),
            Action(
                file="src/Login.tsx",
                line=12,
                role="login-submit",
                evidence=(Evidence("src/Login.tsx", (12, 12)),),
            ),
        ]
    )


def test_plan_includes_flow_graph_block():
    from playwright_god.generator import (
        PlaywrightTestGenerator,
        TemplateLLMClient,
    )

    captured = {}

    class _Capture(TemplateLLMClient):
        def complete(self, prompt, system_prompt=None):
            captured["prompt"] = prompt
            return "PLAN"

    gen = PlaywrightTestGenerator(llm_client=_Capture())
    out = gen.plan(
        "memory map text",
        flow_graph=_flow_graph_with_routes_and_actions(),
    )
    assert out == "PLAN"
    assert "## Flow Graph" in captured["prompt"]
    assert "route:GET:/login" in captured["prompt"]
    assert "action:src/Login.tsx:12#login-submit" in captured["prompt"]


def test_plan_with_prioritize_routes_orders_files():
    from playwright_god.generator import PlaywrightTestGenerator

    coverage = {
        "files": [
            {"path": "api/items.py", "percent": 50.0,
             "uncovered_lines": [1, 2], "covered_lines": [3]},
            {"path": "api/auth.py", "percent": 80.0,
             "uncovered_lines": [9], "covered_lines": [1, 2, 3, 4]},
            {"path": "lib/util.py", "percent": 10.0,
             "uncovered_lines": [1, 2, 3, 4, 5], "covered_lines": [6]},
        ],
        "routes": {"uncovered": ["route:POST:/items", "route:GET:/login"]},
    }
    block = PlaywrightTestGenerator._format_coverage_delta(
        coverage,
        prioritize="routes",
        flow_graph=_flow_graph_with_routes_and_actions(),
    )
    # api/items.py and api/auth.py both touched by uncovered routes;
    # lib/util.py has zero route weight even though its percent is lowest.
    first_line = next(line for line in block.splitlines() if line.startswith("- "))
    assert "api/items.py" in first_line or "api/auth.py" in first_line


def test_plan_prioritize_routes_without_graph_falls_back():
    from playwright_god.generator import PlaywrightTestGenerator

    coverage = {
        "files": [
            {"path": "a.py", "percent": 50.0,
             "uncovered_lines": [1], "covered_lines": [2]},
        ],
    }
    block = PlaywrightTestGenerator._format_coverage_delta(
        coverage, prioritize="routes", flow_graph=None
    )
    assert "a.py" in block


def test_format_flow_graph_for_plan_handles_no_uncovered_routes():
    from playwright_god.generator import PlaywrightTestGenerator

    block = PlaywrightTestGenerator._format_flow_graph_for_plan(
        _flow_graph_with_routes_and_actions(),
        coverage={"routes": {"uncovered": []}},
    )
    assert "all routes covered" in block


def test_format_flow_graph_for_plan_returns_empty_for_none():
    from playwright_god.generator import PlaywrightTestGenerator

    assert PlaywrightTestGenerator._format_flow_graph_for_plan(None) == ""


def test_format_flow_graph_for_plan_returns_empty_for_empty_graph():
    from playwright_god.flow_graph import FlowGraph
    from playwright_god.generator import PlaywrightTestGenerator

    assert PlaywrightTestGenerator._format_flow_graph_for_plan(FlowGraph()) == ""


def test_generate_includes_relevant_routes_block():
    from playwright_god.generator import (
        PlaywrightTestGenerator,
        TemplateLLMClient,
    )

    captured = {}

    class _Capture(TemplateLLMClient):
        def complete(self, prompt, system_prompt=None):
            captured["prompt"] = prompt
            return "TEST"

    gen = PlaywrightTestGenerator(llm_client=_Capture())
    out = gen.generate(
        "Test the login flow and items endpoint",
        flow_graph=_flow_graph_with_routes_and_actions(),
    )
    assert out == "TEST"
    assert "Relevant routes & actions" in captured["prompt"]
    # Both terms appear in the description; both routes should be included.
    assert "route:GET:/login" in captured["prompt"]
    assert "route:POST:/items" in captured["prompt"]


def test_format_flow_graph_subgraph_caps_results():
    from playwright_god.flow_graph import Action, Evidence, FlowGraph, Route
    from playwright_god.generator import PlaywrightTestGenerator

    routes = [Route(method="GET", path=f"/p{i}",
                    evidence=(Evidence("a.py", (i, i)),)) for i in range(20)]
    actions = [Action(file="a.tsx", line=i, role=f"r{i}") for i in range(20)]
    g = FlowGraph.from_iterables(routes + actions)
    block = PlaywrightTestGenerator._format_flow_graph_subgraph(g, "anything", cap=3)
    # 3 routes + 3 actions max
    assert block.count("- route:") <= 3
    assert block.count("- action:") <= 3


def test_format_flow_graph_subgraph_empty_graph_returns_empty():
    from playwright_god.flow_graph import FlowGraph
    from playwright_god.generator import PlaywrightTestGenerator

    assert PlaywrightTestGenerator._format_flow_graph_subgraph(FlowGraph(), "x") == ""


# ---------------------------------------------------------------------------
# PlaywrightCLIClient
# ---------------------------------------------------------------------------


class TestPlaywrightCLIClient:
    """Tests for the PlaywrightCLIClient generation backend."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _mock_proc(self, returncode: int = 0, stderr: str = "") -> MagicMock:
        proc = MagicMock()
        proc.communicate.return_value = ("", stderr)
        proc.returncode = returncode
        return proc

    def _patch_which_found(self):
        return patch("playwright_god.generator.shutil.which", return_value="/usr/bin/npx")

    def _patch_which_missing(self):
        return patch("playwright_god.generator.shutil.which", return_value=None)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def test_default_executable_and_timeout(self):
        client = PlaywrightCLIClient()
        assert client.executable == "npx"
        assert client.timeout == PlaywrightCLIClient.DEFAULT_TIMEOUT
        assert client.url is None

    def test_custom_params_stored(self):
        client = PlaywrightCLIClient(executable="playwright", timeout=60, url="http://localhost")
        assert client.executable == "playwright"
        assert client.timeout == 60
        assert client.url == "http://localhost"

    def test_fallback_is_template_client(self):
        client = PlaywrightCLIClient()
        assert isinstance(client._fallback, TemplateLLMClient)

    # ------------------------------------------------------------------
    # Executable validation
    # ------------------------------------------------------------------

    def test_raises_playwright_cli_error_when_executable_missing(self):
        client = PlaywrightCLIClient()
        with self._patch_which_missing():
            with pytest.raises(PlaywrightCLIError, match="not found on PATH"):
                client.complete("Description: test login")

    def test_error_message_mentions_executable_name(self):
        client = PlaywrightCLIClient(executable="my-npx")
        with patch("playwright_god.generator.shutil.which", return_value=None):
            with pytest.raises(PlaywrightCLIError, match="my-npx"):
                client.complete("Description: test")

    # ------------------------------------------------------------------
    # URL resolution
    # ------------------------------------------------------------------

    def test_falls_back_to_template_when_no_url_in_prompt(self):
        client = PlaywrightCLIClient()
        with self._patch_which_found():
            result = client.complete("Description: test something without a URL")
        assert 'import { test, expect } from "@playwright/test";' in result

    def test_extracts_url_from_prompt(self, tmp_path):
        spec_content = 'import { test, expect } from "@playwright/test";'
        client = PlaywrightCLIClient()
        captured_cmd: list[str] = []

        def fake_popen(cmd, **kwargs):
            captured_cmd.extend(cmd)
            # Write spec to the actual --output path the client will read.
            out_idx = cmd.index("--output")
            with open(cmd[out_idx + 1], "w", encoding="utf-8") as fh:
                fh.write(spec_content)
            return self._mock_proc()

        with (
            self._patch_which_found(),
            patch("playwright_god.generator.subprocess.Popen", side_effect=fake_popen),
        ):
            result = client.complete("Description: test\nhttp://localhost:3000/app")

        assert "http://localhost:3000/app" in captured_cmd
        assert result == spec_content

    def test_explicit_url_overrides_prompt_url(self, tmp_path):
        explicit_url = "http://explicit-host.com"
        spec_content = 'import { test, expect } from "@playwright/test";'
        client = PlaywrightCLIClient(url=explicit_url)
        captured_cmd: list[str] = []

        def fake_popen(cmd, **kwargs):
            captured_cmd.extend(cmd)
            out_idx = cmd.index("--output")
            with open(cmd[out_idx + 1], "w", encoding="utf-8") as fh:
                fh.write(spec_content)
            return self._mock_proc()

        with (
            self._patch_which_found(),
            patch("playwright_god.generator.subprocess.Popen", side_effect=fake_popen),
        ):
            result = client.complete("Description: test\nhttp://localhost:3000")

        assert explicit_url in captured_cmd
        assert "http://localhost:3000" not in [a for a in captured_cmd if a != "--output"]
        assert result == spec_content

    # ------------------------------------------------------------------
    # Subprocess outcome handling
    # ------------------------------------------------------------------

    def test_returns_recorded_code_on_success(self, tmp_path):
        spec_content = (
            'import { test, expect } from "@playwright/test";\n'
            'test("login", async ({ page }) => {\n'
            '  await page.goto("http://localhost:3000");\n'
            "});\n"
        )
        client = PlaywrightCLIClient(url="http://localhost:3000")

        def fake_popen(cmd, **kwargs):
            out_idx = cmd.index("--output")
            out_path = cmd[out_idx + 1]
            with open(out_path, "w", encoding="utf-8") as fh:
                fh.write(spec_content)
            return self._mock_proc(returncode=0)

        with (
            self._patch_which_found(),
            patch("playwright_god.generator.subprocess.Popen", side_effect=fake_popen),
        ):
            result = client.complete("Description: login test")

        assert result == spec_content

    def test_raises_on_non_zero_exit_with_empty_output(self, tmp_path):
        client = PlaywrightCLIClient(url="http://localhost:3000")
        proc = self._mock_proc(returncode=1, stderr="Could not launch browser")

        with (
            self._patch_which_found(),
            patch("playwright_god.generator.subprocess.Popen", return_value=proc),
        ):
            with pytest.raises(PlaywrightCLIError, match="exited with code 1"):
                client.complete("Description: test")

    def test_error_message_includes_stderr(self, tmp_path):
        client = PlaywrightCLIClient(url="http://localhost:3000")
        proc = self._mock_proc(returncode=1, stderr="Browser launch failed")

        with (
            self._patch_which_found(),
            patch("playwright_god.generator.subprocess.Popen", return_value=proc),
        ):
            with pytest.raises(PlaywrightCLIError, match="Browser launch failed"):
                client.complete("Description: test")

    def test_falls_back_to_template_on_zero_exit_with_empty_output(self, tmp_path):
        client = PlaywrightCLIClient(url="http://localhost:3000")
        # Popen succeeds but writes nothing to the output file.
        proc = self._mock_proc(returncode=0)

        with (
            self._patch_which_found(),
            patch("playwright_god.generator.subprocess.Popen", return_value=proc),
        ):
            result = client.complete("Description: login flow")

        assert 'import { test, expect } from "@playwright/test";' in result

    def test_raises_playwright_cli_error_on_timeout(self):
        client = PlaywrightCLIClient(url="http://localhost:3000", timeout=5)
        proc = MagicMock()
        proc.communicate.side_effect = [
            subprocess.TimeoutExpired(cmd=["npx"], timeout=5),
            ("", ""),  # second communicate() after kill()
        ]

        with (
            self._patch_which_found(),
            patch("playwright_god.generator.subprocess.Popen", return_value=proc),
        ):
            with pytest.raises(PlaywrightCLIError, match="timed out after 5s"):
                client.complete("Description: test")

    def test_timeout_error_kills_process(self):
        client = PlaywrightCLIClient(url="http://localhost:3000", timeout=5)
        proc = MagicMock()
        proc.communicate.side_effect = [
            subprocess.TimeoutExpired(cmd=["npx"], timeout=5),
            ("", ""),  # second communicate() after kill()
        ]

        with (
            self._patch_which_found(),
            patch("playwright_god.generator.subprocess.Popen", return_value=proc),
            pytest.raises(PlaywrightCLIError),
        ):
            client.complete("Description: test")

        proc.kill.assert_called_once()

    # ------------------------------------------------------------------
    # Command construction
    # ------------------------------------------------------------------

    def test_command_includes_npx_playwright_codegen(self, tmp_path):
        spec_content = 'import { test, expect } from "@playwright/test";'
        client = PlaywrightCLIClient(url="http://localhost:3000")
        captured_cmd: list[str] = []

        def fake_popen(cmd, **kwargs):
            captured_cmd.extend(cmd)
            out_idx = cmd.index("--output")
            out_path = cmd[out_idx + 1]
            with open(out_path, "w", encoding="utf-8") as fh:
                fh.write(spec_content)
            return self._mock_proc()

        with (
            self._patch_which_found(),
            patch("playwright_god.generator.subprocess.Popen", side_effect=fake_popen),
        ):
            client.complete("Description: test")

        assert captured_cmd[0] == "npx"
        assert "playwright" in captured_cmd
        assert "codegen" in captured_cmd
        assert "--output" in captured_cmd
        assert "http://localhost:3000" in captured_cmd

    def test_temp_file_is_cleaned_up_after_success(self, tmp_path):
        import os

        spec_content = 'import { test, expect } from "@playwright/test";'
        client = PlaywrightCLIClient(url="http://localhost:3000")
        created_paths: list[str] = []

        original_mkstemp = __import__("tempfile").mkstemp

        def fake_mkstemp(**kwargs):
            fd, path = original_mkstemp(**kwargs)
            created_paths.append(path)
            return fd, path

        def fake_popen(cmd, **kwargs):
            out_idx = cmd.index("--output")
            out_path = cmd[out_idx + 1]
            with open(out_path, "w", encoding="utf-8") as fh:
                fh.write(spec_content)
            return self._mock_proc()

        with (
            self._patch_which_found(),
            patch("playwright_god.generator.tempfile.mkstemp", side_effect=fake_mkstemp),
            patch("playwright_god.generator.subprocess.Popen", side_effect=fake_popen),
        ):
            client.complete("Description: test")

        for path in created_paths:
            assert not os.path.exists(path), f"Temp file {path} was not cleaned up"

    def test_temp_file_is_cleaned_up_after_error(self, tmp_path):
        import os

        client = PlaywrightCLIClient(url="http://localhost:3000")
        created_paths: list[str] = []

        original_mkstemp = __import__("tempfile").mkstemp

        def fake_mkstemp(**kwargs):
            fd, path = original_mkstemp(**kwargs)
            created_paths.append(path)
            return fd, path

        proc = self._mock_proc(returncode=1, stderr="error")

        with (
            self._patch_which_found(),
            patch("playwright_god.generator.tempfile.mkstemp", side_effect=fake_mkstemp),
            patch("playwright_god.generator.subprocess.Popen", return_value=proc),
            pytest.raises(PlaywrightCLIError),
        ):
            client.complete("Description: test")

        for path in created_paths:
            assert not os.path.exists(path), f"Temp file {path} was not cleaned up"
