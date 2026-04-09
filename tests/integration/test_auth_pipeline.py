"""Integration tests for the auth-aware RAG pipeline.

Covers SAML, NTLM, OIDC, and basic auth generation paths end-to-end:
crawl → index → generate with auth_type → assert output quality.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from playwright_god.auth_templates import (
    AUTH_TYPES,
    get_auth_hint,
    get_template,
)
from playwright_god.chunker import FileChunker
from playwright_god.crawler import RepositoryCrawler
from playwright_god.embedder import MockEmbedder
from playwright_god.generator import PlaywrightTestGenerator, TemplateLLMClient
from playwright_god.indexer import RepositoryIndexer

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
SAML_APP_DIR = FIXTURES_DIR / "saml_app"


def _unique_indexer() -> RepositoryIndexer:
    return RepositoryIndexer(
        collection_name=f"auth_integ_{uuid.uuid4().hex}",
        persist_dir=None,
        embedder=MockEmbedder(),
    )


def _build_indexer(repo_path: str) -> RepositoryIndexer:
    crawler = RepositoryCrawler()
    files = crawler.crawl(repo_path)
    assert files, "SAML app fixture must contain crawlable files"
    chunker = FileChunker(chunk_size=30, overlap=5)
    chunks = chunker.chunk_files(files)
    indexer = _unique_indexer()
    indexer.add_chunks(chunks)
    return indexer


# ---------------------------------------------------------------------------
# Auth template module
# ---------------------------------------------------------------------------


class TestAuthTemplatesModule:
    def test_get_template_saml_returns_typescript(self):
        tmpl = get_template("saml")
        assert tmpl is not None
        assert "storageState" in tmpl
        assert "waitForURL" in tmpl
        assert "process.env.TEST_USERNAME" in tmpl
        assert "process.env.TEST_PASSWORD" in tmpl

    def test_get_template_ntlm_returns_typescript(self):
        tmpl = get_template("ntlm")
        assert tmpl is not None
        assert "httpCredentials" in tmpl
        assert "process.env.TEST_USERNAME" in tmpl

    def test_get_template_oidc_returns_typescript(self):
        tmpl = get_template("oidc")
        assert tmpl is not None
        assert "storageState" in tmpl
        assert "waitForURL" in tmpl

    def test_get_template_logging_returns_typescript(self):
        tmpl = get_template("logging")
        assert tmpl is not None
        assert "page.on('console'" in tmpl
        assert "page.on('pageerror'" in tmpl
        assert "page.route(" in tmpl

    def test_get_template_none_for_basic(self):
        # basic auth has no multi-step setup snippet
        assert get_template("basic") is None

    def test_get_template_none_for_unknown(self):
        assert get_template("unknown") is None

    def test_get_auth_hint_saml(self):
        hint = get_auth_hint("saml")
        assert hint is not None
        assert "SAML" in hint
        assert "storageState" in hint

    def test_get_auth_hint_ntlm(self):
        hint = get_auth_hint("ntlm")
        assert hint is not None
        assert "NTLM" in hint or "Active Directory" in hint

    def test_get_auth_hint_oidc(self):
        hint = get_auth_hint("oidc")
        assert hint is not None
        assert "OIDC" in hint

    def test_get_auth_hint_basic(self):
        hint = get_auth_hint("basic")
        assert hint is not None
        assert "Basic" in hint

    def test_get_auth_hint_logging(self):
        hint = get_auth_hint("logging")
        assert hint is not None
        assert "console" in hint

    def test_get_auth_hint_none_for_none_type(self):
        assert get_auth_hint("none") is None

    def test_auth_types_contains_expected_values(self):
        for expected in ("saml", "ntlm", "oidc", "basic", "logging", "none"):
            assert expected in AUTH_TYPES


# ---------------------------------------------------------------------------
# Generator.generate with auth_type
# ---------------------------------------------------------------------------


class TestGenerateWithAuthType:
    """Verify that auth hints + templates are injected into the LLM prompt."""

    def _capture_prompt(self, auth_type: str) -> str:
        captured: list[str] = []

        class CapturingLLM:
            def complete(self, prompt: str) -> str:
                captured.append(prompt)
                return "// captured"

        gen = PlaywrightTestGenerator(llm_client=CapturingLLM())
        gen.generate("login flow", auth_type=auth_type)
        assert captured
        return captured[0]

    def test_saml_hint_in_prompt(self):
        prompt = self._capture_prompt("saml")
        assert "SAML" in prompt
        assert "storageState" in prompt

    def test_saml_template_in_prompt(self):
        prompt = self._capture_prompt("saml")
        # The TypeScript template snippet is injected as extra context
        assert "global-setup" in prompt.lower() or "storageState" in prompt

    def test_ntlm_hint_in_prompt(self):
        prompt = self._capture_prompt("ntlm")
        assert "NTLM" in prompt or "httpCredentials" in prompt

    def test_oidc_hint_in_prompt(self):
        prompt = self._capture_prompt("oidc")
        assert "OIDC" in prompt or "storageState" in prompt

    def test_basic_hint_in_prompt(self):
        prompt = self._capture_prompt("basic")
        assert "Basic" in prompt or "httpCredentials" in prompt

    def test_logging_hint_in_prompt(self):
        prompt = self._capture_prompt("logging")
        assert "console" in prompt

    def test_none_auth_type_adds_no_hint(self):
        captured: list[str] = []

        class CapturingLLM:
            def complete(self, prompt: str) -> str:
                captured.append(prompt)
                return "// captured"

        gen = PlaywrightTestGenerator(llm_client=CapturingLLM())
        gen.generate("login flow", auth_type="none")
        # The auth hint block is not injected for auth_type="none"
        assert "Auth type:" not in captured[0]

    def test_extra_context_combined_with_auth_hint(self):
        captured: list[str] = []

        class CapturingLLM:
            def complete(self, prompt: str) -> str:
                captured.append(prompt)
                return "// captured"

        gen = PlaywrightTestGenerator(llm_client=CapturingLLM())
        gen.generate("login", auth_type="saml", extra_context="CUSTOM_EXTRA_MARKER")
        assert "SAML" in captured[0]
        assert "CUSTOM_EXTRA_MARKER" in captured[0]


# ---------------------------------------------------------------------------
# Credential sanitization
# ---------------------------------------------------------------------------


class TestSecretRedaction:
    def _gen_with_output(self, output: str, redact: bool = True) -> str:
        class StaticLLM:
            def complete(self, _prompt: str) -> str:
                return output

        gen = PlaywrightTestGenerator(llm_client=StaticLLM())
        return gen.generate("test", redact_secrets=redact)

    def test_hardcoded_password_replaced(self):
        code = self._gen_with_output('password = "s3cr3t-pass";')
        assert "s3cr3t-pass" not in code
        assert "process.env.TEST_PASSWORD" in code

    def test_hardcoded_username_replaced(self):
        code = self._gen_with_output('username = "admin-user";')
        assert "admin-user" not in code
        assert "process.env.TEST_USERNAME" in code

    def test_env_var_reference_not_replaced(self):
        original = 'password = process.env.TEST_PASSWORD;'
        code = self._gen_with_output(original)
        assert "process.env.TEST_PASSWORD" in code

    def test_placeholder_value_not_replaced(self):
        original = 'password = "CHANGE_ME";'
        code = self._gen_with_output(original)
        # Placeholder patterns are left untouched
        assert "CHANGE_ME" in code

    def test_redact_disabled_leaves_secrets(self):
        original = 'password = "plaintext";'
        code = self._gen_with_output(original, redact=False)
        assert "plaintext" in code


# ---------------------------------------------------------------------------
# Full pipeline: SAML app crawl → generate with auth_type="saml"
# ---------------------------------------------------------------------------


class TestSAMLPipeline:
    def test_saml_app_crawled(self):
        crawler = RepositoryCrawler()
        files = crawler.crawl(str(SAML_APP_DIR))
        file_names = [f.path for f in files]
        assert any("index.html" in p for p in file_names)

    def test_saml_config_json_indexed(self):
        """saml-config.json must not be skipped by the crawler."""
        crawler = RepositoryCrawler()
        files = crawler.crawl(str(SAML_APP_DIR))
        file_names = [f.path for f in files]
        assert any("saml-config.json" in p for p in file_names)

    def test_env_example_indexed(self):
        """.env.example must not be skipped by the crawler."""
        crawler = RepositoryCrawler()
        files = crawler.crawl(str(SAML_APP_DIR))
        file_names = [f.path for f in files]
        assert any(".env.example" in p for p in file_names)

    def test_full_saml_pipeline_generates_storagestate(self):
        """End-to-end: index SAML app, generate with auth_type='saml'."""
        indexer = _build_indexer(str(SAML_APP_DIR))
        generator = PlaywrightTestGenerator(
            llm_client=TemplateLLMClient(),
            indexer=indexer,
        )
        test_code = generator.generate(
            "SAML SSO login flow",
            auth_type="saml",
        )
        assert isinstance(test_code, str)
        assert "@playwright/test" in test_code
        assert "page.goto" in test_code

    def test_saml_prompt_contains_storagestate(self):
        """The prompt sent to the LLM must reference storageState."""
        captured: list[str] = []

        class CapturingLLM:
            def complete(self, prompt: str) -> str:
                captured.append(prompt)
                return "// captured"

        indexer = _build_indexer(str(SAML_APP_DIR))
        gen = PlaywrightTestGenerator(llm_client=CapturingLLM(), indexer=indexer)
        gen.generate("SAML SSO login", auth_type="saml")

        assert captured
        assert "storageState" in captured[0]
        assert "waitForURL" in captured[0]
        assert "process.env" in captured[0]
