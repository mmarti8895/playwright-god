"""Unit tests for playwright_god.cli."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from playwright_god.cli import cli


@pytest.fixture()
def runner():
    return CliRunner()


class TestIndexCommand:
    def test_index_help(self, runner):
        result = runner.invoke(cli, ["index", "--help"])
        assert result.exit_code == 0
        assert "REPO_PATH" in result.output or "repo_path" in result.output.lower()

    def test_index_sample_app(self, runner, sample_repo_path, tmp_path):
        persist = str(tmp_path / "idx")
        with (
            patch("playwright_god.cli.DefaultEmbedder") as MockEmb,
            patch("playwright_god.cli.RepositoryIndexer") as MockIdx,
        ):
            mock_emb = MagicMock()
            MockEmb.return_value = mock_emb
            mock_indexer = MagicMock()
            mock_indexer.count.return_value = 42
            MockIdx.return_value = mock_indexer

            result = runner.invoke(cli, ["index", sample_repo_path, "-d", persist])

        assert result.exit_code == 0
        assert "Found" in result.output
        assert "42" in result.output

    def test_index_missing_directory(self, runner):
        result = runner.invoke(cli, ["index", "/nonexistent/path/abc"])
        assert result.exit_code != 0

    def test_index_empty_directory(self, runner, tmp_path):
        result = runner.invoke(cli, ["index", str(tmp_path)])
        assert result.exit_code != 0


class TestGenerateCommand:
    def test_generate_help(self, runner):
        result = runner.invoke(cli, ["generate", "--help"])
        assert result.exit_code == 0
        assert "DESCRIPTION" in result.output or "description" in result.output.lower()

    def test_generate_template_fallback(self, runner, tmp_path):
        """generate should use TemplateLLMClient when OPENAI_API_KEY is absent."""
        persist = str(tmp_path / "idx")
        with (
            patch("playwright_god.cli.DefaultEmbedder") as MockEmb,
            patch("playwright_god.cli.RepositoryIndexer") as MockIdx,
            patch.dict("os.environ", {}, clear=False),
        ):
            mock_emb = MagicMock()
            MockEmb.return_value = mock_emb
            mock_indexer = MagicMock()
            mock_indexer.count.return_value = 5
            mock_indexer.search.return_value = []
            MockIdx.return_value = mock_indexer

            # Ensure no API key
            os.environ.pop("OPENAI_API_KEY", None)

            result = runner.invoke(
                cli,
                ["generate", "test the login page", "-d", persist],
            )

        assert result.exit_code == 0
        assert "@playwright/test" in result.output or "playwright" in result.output.lower()

    def test_generate_writes_output_file(self, runner, tmp_path):
        persist = str(tmp_path / "idx")
        output_file = str(tmp_path / "test.spec.ts")

        with (
            patch("playwright_god.cli.DefaultEmbedder") as MockEmb,
            patch("playwright_god.cli.RepositoryIndexer") as MockIdx,
        ):
            mock_emb = MagicMock()
            MockEmb.return_value = mock_emb
            mock_indexer = MagicMock()
            mock_indexer.count.return_value = 0
            mock_indexer.search.return_value = []
            MockIdx.return_value = mock_indexer

            os.environ.pop("OPENAI_API_KEY", None)

            result = runner.invoke(
                cli,
                ["generate", "login form test", "-d", persist, "-o", output_file],
            )

        assert result.exit_code == 0
        assert Path(output_file).exists()
        content = Path(output_file).read_text()
        assert len(content) > 0

    def test_generate_warns_empty_index(self, runner, tmp_path):
        persist = str(tmp_path / "idx")
        with (
            patch("playwright_god.cli.DefaultEmbedder") as MockEmb,
            patch("playwright_god.cli.RepositoryIndexer") as MockIdx,
        ):
            mock_emb = MagicMock()
            MockEmb.return_value = mock_emb
            mock_indexer = MagicMock()
            mock_indexer.count.return_value = 0
            mock_indexer.search.return_value = []
            MockIdx.return_value = mock_indexer

            os.environ.pop("OPENAI_API_KEY", None)

            # mix_stderr=True (default) so stderr is merged into result.output
            result = runner.invoke(
                cli,
                ["generate", "some description", "-d", persist],
            )

        assert result.exit_code == 0
        # The warning is written to stderr (merged into output here)
        assert "Warning" in result.output or "empty" in result.output.lower()

    def _make_mock_indexer(self, MockEmb, MockIdx):
        mock_emb = MagicMock()
        MockEmb.return_value = mock_emb
        mock_indexer = MagicMock()
        mock_indexer.count.return_value = 5
        mock_indexer.search.return_value = []
        MockIdx.return_value = mock_indexer

    def test_generate_provider_help_lists_providers(self, runner):
        result = runner.invoke(cli, ["generate", "--help"])
        assert result.exit_code == 0
        assert "openai" in result.output
        assert "anthropic" in result.output
        assert "gemini" in result.output
        assert "ollama" in result.output

    def test_generate_explicit_template_provider(self, runner, tmp_path):
        persist = str(tmp_path / "idx")
        with (
            patch("playwright_god.cli.DefaultEmbedder") as MockEmb,
            patch("playwright_god.cli.RepositoryIndexer") as MockIdx,
        ):
            self._make_mock_indexer(MockEmb, MockIdx)
            result = runner.invoke(
                cli,
                ["generate", "test something", "-d", persist, "--provider", "template"],
            )
        assert result.exit_code == 0
        assert "@playwright/test" in result.output or "playwright" in result.output.lower()

    def test_generate_openai_provider_selected(self, runner, tmp_path):
        persist = str(tmp_path / "idx")
        with (
            patch("playwright_god.cli.DefaultEmbedder") as MockEmb,
            patch("playwright_god.cli.RepositoryIndexer") as MockIdx,
            patch("playwright_god.cli.OpenAIClient") as MockOpenAI,
        ):
            self._make_mock_indexer(MockEmb, MockIdx)
            mock_client = MagicMock()
            mock_client.complete.return_value = "// openai test"
            MockOpenAI.return_value = mock_client

            result = runner.invoke(
                cli,
                [
                    "generate", "login flow", "-d", persist,
                    "--provider", "openai", "--api-key", "sk-test",
                ],
            )

        assert result.exit_code == 0
        MockOpenAI.assert_called_once_with(api_key="sk-test", model="gpt-4o")

    def test_generate_openai_custom_model(self, runner, tmp_path):
        persist = str(tmp_path / "idx")
        with (
            patch("playwright_god.cli.DefaultEmbedder") as MockEmb,
            patch("playwright_god.cli.RepositoryIndexer") as MockIdx,
            patch("playwright_god.cli.OpenAIClient") as MockOpenAI,
        ):
            self._make_mock_indexer(MockEmb, MockIdx)
            mock_client = MagicMock()
            mock_client.complete.return_value = "// openai test"
            MockOpenAI.return_value = mock_client

            result = runner.invoke(
                cli,
                [
                    "generate", "login flow", "-d", persist,
                    "--provider", "openai", "--api-key", "sk-test",
                    "--model", "gpt-4-turbo",
                ],
            )

        assert result.exit_code == 0
        MockOpenAI.assert_called_once_with(api_key="sk-test", model="gpt-4-turbo")

    def test_generate_anthropic_provider_selected(self, runner, tmp_path):
        persist = str(tmp_path / "idx")
        with (
            patch("playwright_god.cli.DefaultEmbedder") as MockEmb,
            patch("playwright_god.cli.RepositoryIndexer") as MockIdx,
            patch("playwright_god.cli.AnthropicClient") as MockAnthropic,
        ):
            self._make_mock_indexer(MockEmb, MockIdx)
            mock_client = MagicMock()
            mock_client.complete.return_value = "// anthropic test"
            MockAnthropic.return_value = mock_client

            result = runner.invoke(
                cli,
                [
                    "generate", "login flow", "-d", persist,
                    "--provider", "anthropic", "--api-key", "ant-test",
                ],
            )

        assert result.exit_code == 0
        MockAnthropic.assert_called_once_with(
            api_key="ant-test", model="claude-3-5-sonnet-20241022"
        )

    def test_generate_gemini_provider_selected(self, runner, tmp_path):
        persist = str(tmp_path / "idx")
        with (
            patch("playwright_god.cli.DefaultEmbedder") as MockEmb,
            patch("playwright_god.cli.RepositoryIndexer") as MockIdx,
            patch("playwright_god.cli.GeminiClient") as MockGemini,
        ):
            self._make_mock_indexer(MockEmb, MockIdx)
            mock_client = MagicMock()
            mock_client.complete.return_value = "// gemini test"
            MockGemini.return_value = mock_client

            result = runner.invoke(
                cli,
                [
                    "generate", "login flow", "-d", persist,
                    "--provider", "gemini", "--api-key", "gem-test",
                ],
            )

        assert result.exit_code == 0
        MockGemini.assert_called_once_with(api_key="gem-test", model="gemini-1.5-pro")

    def test_generate_ollama_provider_selected(self, runner, tmp_path):
        persist = str(tmp_path / "idx")
        with (
            patch("playwright_god.cli.DefaultEmbedder") as MockEmb,
            patch("playwright_god.cli.RepositoryIndexer") as MockIdx,
            patch("playwright_god.cli.OllamaClient") as MockOllama,
        ):
            self._make_mock_indexer(MockEmb, MockIdx)
            mock_client = MagicMock()
            mock_client.complete.return_value = "// ollama test"
            MockOllama.return_value = mock_client

            result = runner.invoke(
                cli,
                [
                    "generate", "login flow", "-d", persist,
                    "--provider", "ollama", "--model", "mistral",
                ],
            )

        assert result.exit_code == 0
        MockOllama.assert_called_once_with(
            model="mistral", base_url="http://localhost:11434"
        )

    def test_generate_ollama_custom_url(self, runner, tmp_path):
        persist = str(tmp_path / "idx")
        with (
            patch("playwright_god.cli.DefaultEmbedder") as MockEmb,
            patch("playwright_god.cli.RepositoryIndexer") as MockIdx,
            patch("playwright_god.cli.OllamaClient") as MockOllama,
        ):
            self._make_mock_indexer(MockEmb, MockIdx)
            mock_client = MagicMock()
            mock_client.complete.return_value = "// ollama test"
            MockOllama.return_value = mock_client

            result = runner.invoke(
                cli,
                [
                    "generate", "login flow", "-d", persist,
                    "--provider", "ollama", "--ollama-url", "http://myserver:11434",
                ],
            )

        assert result.exit_code == 0
        MockOllama.assert_called_once_with(
            model="llama3", base_url="http://myserver:11434"
        )

    def test_generate_autodetects_anthropic_key(self, runner, tmp_path):
        persist = str(tmp_path / "idx")
        os.environ.pop("OPENAI_API_KEY", None)
        with (
            patch("playwright_god.cli.DefaultEmbedder") as MockEmb,
            patch("playwright_god.cli.RepositoryIndexer") as MockIdx,
            patch("playwright_god.cli.AnthropicClient") as MockAnthropic,
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "ant-auto"}, clear=False),
        ):
            self._make_mock_indexer(MockEmb, MockIdx)
            mock_client = MagicMock()
            mock_client.complete.return_value = "// anthropic auto"
            MockAnthropic.return_value = mock_client

            result = runner.invoke(
                cli,
                ["generate", "login flow", "-d", persist],
            )

        assert result.exit_code == 0
        MockAnthropic.assert_called_once()

    def test_generate_autodetects_gemini_key(self, runner, tmp_path):
        persist = str(tmp_path / "idx")
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("ANTHROPIC_API_KEY", None)
        with (
            patch("playwright_god.cli.DefaultEmbedder") as MockEmb,
            patch("playwright_god.cli.RepositoryIndexer") as MockIdx,
            patch("playwright_god.cli.GeminiClient") as MockGemini,
            patch.dict("os.environ", {"GOOGLE_API_KEY": "gem-auto"}, clear=False),
        ):
            self._make_mock_indexer(MockEmb, MockIdx)
            mock_client = MagicMock()
            mock_client.complete.return_value = "// gemini auto"
            MockGemini.return_value = mock_client

            result = runner.invoke(
                cli,
                ["generate", "login flow", "-d", persist],
            )

        assert result.exit_code == 0
        MockGemini.assert_called_once()

    def test_generate_invalid_provider_fails(self, runner, tmp_path):
        persist = str(tmp_path / "idx")
        result = runner.invoke(
            cli,
            ["generate", "login flow", "-d", persist, "--provider", "unknown_llm"],
        )
        assert result.exit_code != 0
