"""Unit tests for playwright_god.cli."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from playwright_god.cli import cli, main
from playwright_god.runner import RunResult


# Variables that the CLI's provider-resolution logic reads from the environment.
# Cleared automatically before every test so that the developer's local `.env`
# (loaded by `load_dotenv` at `cli` import time) cannot influence assertions.
_LLM_ENV_VARS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "PLAYWRIGHT_GOD_PROVIDER",
    "PLAYWRIGHT_GOD_MODEL",
    "OLLAMA_URL",
)


@pytest.fixture(autouse=True)
def _clear_llm_env(monkeypatch):
    """Ensure CLI tests run with no LLM provider env vars set.

    Tests that need a key set should call `monkeypatch.setenv(...)` themselves.
    """
    for var in _LLM_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


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
            patch("playwright_god.cli.format_feature_summary") as MockSummary,
        ):
            mock_emb = MagicMock()
            MockEmb.return_value = mock_emb
            mock_indexer = MagicMock()
            mock_indexer.count.return_value = 42
            MockIdx.return_value = mock_indexer
            MockSummary.return_value = "Feature areas inferred:\n  - Authentication"

            result = runner.invoke(cli, ["index", sample_repo_path, "-d", persist])

        assert result.exit_code == 0
        assert "Found" in result.output
        assert "Feature areas inferred" in result.output
        assert "42" in result.output

    def test_index_missing_directory(self, runner):
        result = runner.invoke(cli, ["index", "/nonexistent/path/abc"])
        assert result.exit_code != 0

    def test_index_empty_directory(self, runner, tmp_path):
        result = runner.invoke(cli, ["index", str(tmp_path)])
        assert result.exit_code != 0

    def test_index_adds_extra_file(self, runner, sample_repo_path, tmp_path):
        persist = str(tmp_path / "idx")
        extra_file = tmp_path / "saml-config.json"
        extra_file.write_text('{"issuer":"example"}', encoding="utf-8")

        with (
            patch("playwright_god.cli.DefaultEmbedder") as MockEmb,
            patch("playwright_god.cli.RepositoryIndexer") as MockIdx,
        ):
            mock_emb = MagicMock()
            MockEmb.return_value = mock_emb
            mock_indexer = MagicMock()
            mock_indexer.count.return_value = 5
            MockIdx.return_value = mock_indexer

            result = runner.invoke(
                cli,
                ["index", sample_repo_path, "-d", persist, "-e", str(extra_file)],
            )

        assert result.exit_code == 0
        assert "Added extra file" in result.output

    def test_index_warns_when_extra_file_cannot_be_read(self, runner, sample_repo_path, tmp_path):
        persist = str(tmp_path / "idx")
        extra_file = tmp_path / "broken.json"
        extra_file.write_text("{}", encoding="utf-8")
        original_read_text = Path.read_text

        def failing_read_text(self, *args, **kwargs):
            if self == extra_file:
                raise OSError("boom")
            return original_read_text(self, *args, **kwargs)

        with (
            patch("playwright_god.cli.DefaultEmbedder") as MockEmb,
            patch("playwright_god.cli.RepositoryIndexer") as MockIdx,
            patch("playwright_god.cli.Path.read_text", new=failing_read_text),
        ):
            mock_emb = MagicMock()
            MockEmb.return_value = mock_emb
            mock_indexer = MagicMock()
            mock_indexer.count.return_value = 5
            MockIdx.return_value = mock_indexer

            result = runner.invoke(
                cli,
                ["index", sample_repo_path, "-d", persist, "-e", str(extra_file)],
            )

        assert result.exit_code == 0
        assert "Warning: could not read" in result.output


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
        assert 'import { test, expect } from "@playwright/test";' in result.output

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
        assert 'test("' in content

    def test_generate_rejects_directory_output_path(self, runner, tmp_path):
        result = runner.invoke(
            cli,
            ["generate", "login form test", "-o", str(tmp_path)],
        )

        assert result.exit_code != 0
        assert "File" in result.output
        assert "is a directory" in result.output

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
        assert 'import { test, expect } from "@playwright/test";' in result.output

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

    def test_generate_autodetects_openai_key(self, runner, tmp_path):
        persist = str(tmp_path / "idx")
        with (
            patch("playwright_god.cli.DefaultEmbedder") as MockEmb,
            patch("playwright_god.cli.RepositoryIndexer") as MockIdx,
            patch("playwright_god.cli.OpenAIClient") as MockOpenAI,
            patch.dict("os.environ", {"OPENAI_API_KEY": "sk-auto"}, clear=False),
        ):
            self._make_mock_indexer(MockEmb, MockIdx)
            mock_client = MagicMock()
            mock_client.complete.return_value = "# openai auto"
            MockOpenAI.return_value = mock_client

            result = runner.invoke(cli, ["generate", "login flow", "-d", persist])

        assert result.exit_code == 0
        MockOpenAI.assert_called_once()

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

    def test_generate_with_memory_map(self, runner, tmp_path):
        """generate should load and inject memory map context when --memory-map is given."""
        import json
        persist = str(tmp_path / "idx")
        map_file = str(tmp_path / "map.json")
        map_data = {
            "generated_at": "2024-01-01T00:00:00+00:00",
            "total_files": 1,
            "total_chunks": 1,
            "languages": {"typescript": 1},
            "files": [
                {
                    "path": "src/app.ts",
                    "language": "typescript",
                    "chunks": [{"chunk_id": "abc", "start_line": 1, "end_line": 80}],
                }
            ],
        }
        with open(map_file, "w") as f:
            json.dump(map_data, f)

        with (
            patch("playwright_god.cli.DefaultEmbedder") as MockEmb,
            patch("playwright_god.cli.RepositoryIndexer") as MockIdx,
        ):
            self._make_mock_indexer(MockEmb, MockIdx)
            os.environ.pop("OPENAI_API_KEY", None)

            result = runner.invoke(
                cli,
                [
                    "generate", "test something",
                    "-d", persist,
                    "--provider", "template",
                    "--memory-map", map_file,
                ],
            )

        assert result.exit_code == 0
        assert "Memory map loaded" in result.output
        assert 'import { test, expect } from "@playwright/test";' in result.output
        # must NOT produce a Markdown plan
        assert "# Playwright Test Plan" not in result.output

    def test_generate_memory_map_invalid_file_warns(self, runner, tmp_path):
        """generate should warn but continue when the memory map JSON is invalid."""
        persist = str(tmp_path / "idx")
        bad_map = tmp_path / "bad.json"
        bad_map.write_text("not-json", encoding="utf-8")

        with (
            patch("playwright_god.cli.DefaultEmbedder") as MockEmb,
            patch("playwright_god.cli.RepositoryIndexer") as MockIdx,
        ):
            self._make_mock_indexer(MockEmb, MockIdx)
            os.environ.pop("OPENAI_API_KEY", None)

            result = runner.invoke(
                cli,
                [
                    "generate", "test something",
                    "-d", persist,
                    "--provider", "template",
                    "--memory-map", str(bad_map),
                ],
            )

        assert result.exit_code == 0
        assert "Warning" in result.output

    def test_generate_reads_auth_config_and_env_file(self, runner, tmp_path):
        persist = str(tmp_path / "idx")
        auth_config = tmp_path / "auth.json"
        env_file = tmp_path / ".env"
        auth_config.write_text('{"issuer":"https://idp.example.com"}', encoding="utf-8")
        env_file.write_text("TEST_USERNAME=alice\nTEST_PASSWORD=secret\n", encoding="utf-8")

        with (
            patch("playwright_god.cli.DefaultEmbedder") as MockEmb,
            patch("playwright_god.cli.RepositoryIndexer") as MockIdx,
            patch("playwright_god.cli.TemplateLLMClient") as MockTemplate,
        ):
            self._make_mock_indexer(MockEmb, MockIdx)
            mock_client = MagicMock()
            mock_client.complete.return_value = "def test_example(page):\n    pass\n"
            MockTemplate.return_value = mock_client

            result = runner.invoke(
                cli,
                [
                    "generate",
                    "login flow",
                    "-d",
                    persist,
                    "--provider",
                    "template",
                    "--auth-type",
                    "saml",
                    "--auth-config",
                    str(auth_config),
                    "--env-file",
                    str(env_file),
                ],
            )

        assert result.exit_code == 0
        called_prompt = mock_client.complete.call_args[0][0]
        assert "issuer" in called_prompt
        assert 'process.env.TEST_USERNAME ?? ""' in called_prompt
        assert "Auth type: saml" in result.output

    def test_generate_warns_when_auth_config_cannot_be_read(self, runner, tmp_path):
        persist = str(tmp_path / "idx")
        auth_config = tmp_path / "auth.json"
        auth_config.write_text("{}", encoding="utf-8")

        with (
            patch("playwright_god.cli.DefaultEmbedder") as MockEmb,
            patch("playwright_god.cli.RepositoryIndexer") as MockIdx,
            patch("builtins.open", side_effect=OSError("boom")),
        ):
            self._make_mock_indexer(MockEmb, MockIdx)
            result = runner.invoke(
                cli,
                [
                    "generate",
                    "login flow",
                    "-d",
                    persist,
                    "--provider",
                    "template",
                    "--auth-config",
                    str(auth_config),
                ],
            )

        assert result.exit_code == 0
        assert "Warning: could not read --auth-config" in result.output

    def test_generate_warns_when_env_file_cannot_be_read(self, runner, tmp_path):
        persist = str(tmp_path / "idx")
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_USERNAME=alice\n", encoding="utf-8")

        with (
            patch("playwright_god.cli.DefaultEmbedder") as MockEmb,
            patch("playwright_god.cli.RepositoryIndexer") as MockIdx,
            patch("builtins.open", side_effect=OSError("boom")),
        ):
            self._make_mock_indexer(MockEmb, MockIdx)
            result = runner.invoke(
                cli,
                [
                    "generate",
                    "login flow",
                    "-d",
                    persist,
                    "--provider",
                    "template",
                    "--env-file",
                    str(env_file),
                ],
            )

        assert result.exit_code == 0
        assert "Warning: could not read --env-file" in result.output


class TestIndexMemoryMapFlag:
    def test_index_saves_memory_map(self, runner, sample_repo_path, tmp_path):
        persist = str(tmp_path / "idx")
        map_file = str(tmp_path / "map.json")

        with (
            patch("playwright_god.cli.DefaultEmbedder") as MockEmb,
            patch("playwright_god.cli.RepositoryIndexer") as MockIdx,
            patch("playwright_god.cli.build_memory_map") as MockBuildMap,
            patch("playwright_god.cli.save_memory_map") as MockSaveMap,
        ):
            mock_emb = MagicMock()
            MockEmb.return_value = mock_emb
            mock_indexer = MagicMock()
            mock_indexer.count.return_value = 5
            MockIdx.return_value = mock_indexer
            MockBuildMap.return_value = {"total_files": 2}

            result = runner.invoke(
                cli,
                ["index", sample_repo_path, "-d", persist, "--memory-map", map_file],
            )

        assert result.exit_code == 0
        MockBuildMap.assert_called_once()
        assert "repository_feature_map" in MockBuildMap.call_args.kwargs
        MockSaveMap.assert_called_once()
        assert "Memory map saved" in result.output

    def test_index_no_memory_map_flag_skips_save(self, runner, sample_repo_path, tmp_path):
        persist = str(tmp_path / "idx")

        with (
            patch("playwright_god.cli.DefaultEmbedder") as MockEmb,
            patch("playwright_god.cli.RepositoryIndexer") as MockIdx,
            patch("playwright_god.cli.save_memory_map") as MockSaveMap,
        ):
            mock_emb = MagicMock()
            MockEmb.return_value = mock_emb
            mock_indexer = MagicMock()
            mock_indexer.count.return_value = 5
            MockIdx.return_value = mock_indexer

            result = runner.invoke(
                cli,
                ["index", sample_repo_path, "-d", persist],
            )

        assert result.exit_code == 0
        MockSaveMap.assert_not_called()
        assert "Memory map" not in result.output


class TestPlanCommand:
    def test_plan_help(self, runner):
        result = runner.invoke(cli, ["plan", "--help"])
        assert result.exit_code == 0
        assert "memory-map" in result.output or "memory_map" in result.output.lower()

    def test_plan_with_memory_map_file(self, runner, tmp_path):
        import json
        map_file = str(tmp_path / "map.json")
        map_data = {
            "generated_at": "2024-01-01T00:00:00+00:00",
            "total_files": 2,
            "total_chunks": 3,
            "languages": {"typescript": 2},
            "files": [
                {
                    "path": "src/auth.ts",
                    "language": "typescript",
                    "chunks": [{"chunk_id": "a1", "start_line": 1, "end_line": 80}],
                },
                {
                    "path": "src/login.ts",
                    "language": "typescript",
                    "chunks": [
                        {"chunk_id": "b1", "start_line": 1, "end_line": 80},
                        {"chunk_id": "b2", "start_line": 71, "end_line": 120},
                    ],
                },
            ],
        }
        with open(map_file, "w") as f:
            json.dump(map_data, f)

        os.environ.pop("OPENAI_API_KEY", None)
        result = runner.invoke(
            cli,
            ["plan", "--memory-map", map_file, "--provider", "template"],
        )

        assert result.exit_code == 0
        # Template plan outputs Markdown
        assert "Test Plan" in result.output or "test" in result.output.lower()

    def test_plan_writes_output_file(self, runner, tmp_path):
        import json
        map_file = str(tmp_path / "map.json")
        output_file = str(tmp_path / "plan.md")
        map_data = {
            "generated_at": "2024-01-01T00:00:00+00:00",
            "total_files": 1,
            "total_chunks": 1,
            "languages": {"python": 1},
            "files": [
                {
                    "path": "app.py",
                    "language": "python",
                    "chunks": [{"chunk_id": "x1", "start_line": 1, "end_line": 50}],
                }
            ],
        }
        with open(map_file, "w") as f:
            json.dump(map_data, f)

        os.environ.pop("OPENAI_API_KEY", None)
        result = runner.invoke(
            cli,
            ["plan", "--memory-map", map_file, "--provider", "template", "-o", output_file],
        )

        assert result.exit_code == 0
        from pathlib import Path
        assert Path(output_file).exists()
        content = Path(output_file).read_text()
        assert len(content) > 0

    def test_plan_output_rejects_directory(self, runner, tmp_path):
        import json
        map_file = str(tmp_path / "map.json")
        map_data = {
            "generated_at": "2024-01-01T00:00:00+00:00",
            "total_files": 1,
            "total_chunks": 1,
            "languages": {"python": 1},
            "files": [],
        }
        with open(map_file, "w") as f:
            json.dump(map_data, f)

        result = runner.invoke(
            cli,
            ["plan", "--memory-map", map_file, "--provider", "template", "-o", str(tmp_path)],
        )

        assert result.exit_code != 0

    def test_plan_missing_memory_map_errors(self, runner, tmp_path):
        """plan should exit with an error when the memory map file does not exist."""
        result = runner.invoke(
            cli,
            ["plan", "--memory-map", str(tmp_path / "nonexistent.json")],
        )
        assert result.exit_code != 0

    def test_plan_invalid_memory_map_content_errors(self, runner, tmp_path):
        map_file = tmp_path / "map.json"
        map_file.write_text("{}", encoding="utf-8")
        with patch("playwright_god.cli.load_memory_map", side_effect=ValueError("bad json")):
            result = runner.invoke(cli, ["plan", "--memory-map", str(map_file)])
        assert result.exit_code != 0

    def test_plan_with_focus(self, runner, tmp_path):
        import json
        map_file = str(tmp_path / "map.json")
        map_data = {
            "generated_at": "2024-01-01T00:00:00+00:00",
            "total_files": 1,
            "total_chunks": 1,
            "languages": {"typescript": 1},
            "files": [
                {
                    "path": "src/checkout.ts",
                    "language": "typescript",
                    "chunks": [{"chunk_id": "c1", "start_line": 1, "end_line": 80}],
                }
            ],
        }
        with open(map_file, "w") as f:
            json.dump(map_data, f)

        os.environ.pop("OPENAI_API_KEY", None)
        result = runner.invoke(
            cli,
            ["plan", "--memory-map", map_file, "--provider", "template", "--focus", "checkout"],
        )

        assert result.exit_code == 0
        assert "checkout" in result.output.lower()

    def test_plan_without_memory_map_uses_index(self, runner, tmp_path):
        """plan without --memory-map should fall back to building from the index."""
        persist = str(tmp_path / "idx")
        with patch("playwright_god.cli.RepositoryIndexer") as MockIdx:
            mock_indexer = MagicMock()
            mock_indexer.count.return_value = 2
            from playwright_god.chunker import Chunk
            mock_indexer.get_chunk_stubs.return_value = [
                Chunk(file_path="src/a.ts", content="", start_line=1, end_line=80, language="typescript", chunk_id="c1"),
                Chunk(file_path="src/b.ts", content="", start_line=1, end_line=80, language="typescript", chunk_id="c2"),
            ]
            MockIdx.return_value = mock_indexer

            os.environ.pop("OPENAI_API_KEY", None)
            result = runner.invoke(
                cli,
                ["plan", "-d", persist, "--provider", "template"],
            )

        assert result.exit_code == 0
        # Verify the public helper (not the private _collection) was used
        mock_indexer.get_chunk_stubs.assert_called_once()

    def test_plan_empty_index_errors(self, runner, tmp_path):
        persist = str(tmp_path / "idx")
        with patch("playwright_god.cli.RepositoryIndexer") as MockIdx:
            mock_indexer = MagicMock()
            mock_indexer.count.return_value = 0
            MockIdx.return_value = mock_indexer
            result = runner.invoke(cli, ["plan", "-d", persist])
        assert result.exit_code != 0

    def test_plan_openai_provider_selected(self, runner, tmp_path):
        map_file = tmp_path / "map.json"
        map_file.write_text("{}", encoding="utf-8")
        with (
            patch("playwright_god.cli.load_memory_map", return_value={"total_files": 0, "total_chunks": 0, "languages": {}, "files": []}),
            patch("playwright_god.cli.OpenAIClient") as MockOpenAI,
        ):
            mock_client = MagicMock()
            mock_client.complete.return_value = "# plan"
            MockOpenAI.return_value = mock_client
            result = runner.invoke(
                cli,
                ["plan", "--memory-map", str(map_file), "--provider", "openai", "--api-key", "sk-test"],
            )
        assert result.exit_code == 0
        MockOpenAI.assert_called_once_with(api_key="sk-test", model="gpt-4o")

    def test_plan_anthropic_provider_selected(self, runner, tmp_path):
        map_file = tmp_path / "map.json"
        map_file.write_text("{}", encoding="utf-8")
        with (
            patch("playwright_god.cli.load_memory_map", return_value={"total_files": 0, "total_chunks": 0, "languages": {}, "files": []}),
            patch("playwright_god.cli.AnthropicClient") as MockAnthropic,
        ):
            mock_client = MagicMock()
            mock_client.complete.return_value = "# plan"
            MockAnthropic.return_value = mock_client
            result = runner.invoke(
                cli,
                ["plan", "--memory-map", str(map_file), "--provider", "anthropic", "--api-key", "ant-test"],
            )
        assert result.exit_code == 0
        MockAnthropic.assert_called_once_with(api_key="ant-test", model="claude-3-5-sonnet-20241022")

    def test_plan_gemini_provider_selected(self, runner, tmp_path):
        map_file = tmp_path / "map.json"
        map_file.write_text("{}", encoding="utf-8")
        with (
            patch("playwright_god.cli.load_memory_map", return_value={"total_files": 0, "total_chunks": 0, "languages": {}, "files": []}),
            patch("playwright_god.cli.GeminiClient") as MockGemini,
        ):
            mock_client = MagicMock()
            mock_client.complete.return_value = "# plan"
            MockGemini.return_value = mock_client
            result = runner.invoke(
                cli,
                ["plan", "--memory-map", str(map_file), "--provider", "gemini", "--api-key", "gem-test"],
            )
        assert result.exit_code == 0
        MockGemini.assert_called_once_with(api_key="gem-test", model="gemini-1.5-pro")

    def test_plan_ollama_provider_selected(self, runner, tmp_path):
        map_file = tmp_path / "map.json"
        map_file.write_text("{}", encoding="utf-8")
        with (
            patch("playwright_god.cli.load_memory_map", return_value={"total_files": 0, "total_chunks": 0, "languages": {}, "files": []}),
            patch("playwright_god.cli.OllamaClient") as MockOllama,
        ):
            mock_client = MagicMock()
            mock_client.complete.return_value = "# plan"
            MockOllama.return_value = mock_client
            result = runner.invoke(
                cli,
                ["plan", "--memory-map", str(map_file), "--provider", "ollama", "--model", "mistral"],
            )
        assert result.exit_code == 0
        MockOllama.assert_called_once_with(model="mistral", base_url="http://localhost:11434")

    def test_plan_autodetects_openai_key(self, runner, tmp_path):
        map_file = tmp_path / "map.json"
        map_file.write_text("{}", encoding="utf-8")
        with (
            patch("playwright_god.cli.load_memory_map", return_value={"total_files": 0, "total_chunks": 0, "languages": {}, "files": []}),
            patch("playwright_god.cli.OpenAIClient") as MockOpenAI,
            patch.dict("os.environ", {"OPENAI_API_KEY": "sk-auto"}, clear=False),
        ):
            mock_client = MagicMock()
            mock_client.complete.return_value = "# plan"
            MockOpenAI.return_value = mock_client
            result = runner.invoke(cli, ["plan", "--memory-map", str(map_file)])
        assert result.exit_code == 0
        MockOpenAI.assert_called_once()

    def test_plan_autodetects_anthropic_key(self, runner, tmp_path):
        map_file = tmp_path / "map.json"
        map_file.write_text("{}", encoding="utf-8")
        with (
            patch("playwright_god.cli.load_memory_map", return_value={"total_files": 0, "total_chunks": 0, "languages": {}, "files": []}),
            patch("playwright_god.cli.AnthropicClient") as MockAnthropic,
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "ant-auto"}, clear=False),
        ):
            mock_client = MagicMock()
            mock_client.complete.return_value = "# plan"
            MockAnthropic.return_value = mock_client
            result = runner.invoke(cli, ["plan", "--memory-map", str(map_file)])
        assert result.exit_code == 0
        MockAnthropic.assert_called_once()

    def test_plan_autodetects_gemini_key(self, runner, tmp_path):
        map_file = tmp_path / "map.json"
        map_file.write_text("{}", encoding="utf-8")
        with (
            patch("playwright_god.cli.load_memory_map", return_value={"total_files": 0, "total_chunks": 0, "languages": {}, "files": []}),
            patch("playwright_god.cli.GeminiClient") as MockGemini,
            patch.dict("os.environ", {"GOOGLE_API_KEY": "gem-auto"}, clear=False),
        ):
            mock_client = MagicMock()
            mock_client.complete.return_value = "# plan"
            MockGemini.return_value = mock_client
            result = runner.invoke(cli, ["plan", "--memory-map", str(map_file)])
        assert result.exit_code == 0
        MockGemini.assert_called_once()

    def test_plan_autodetects_template_when_no_keys_are_present(self, runner, tmp_path):
        map_file = tmp_path / "map.json"
        map_file.write_text("{}", encoding="utf-8")
        with (
            patch("playwright_god.cli.load_memory_map", return_value={"total_files": 0, "total_chunks": 0, "languages": {}, "files": []}),
            patch("playwright_god.cli.TemplateLLMClient") as MockTemplate,
            patch.dict("os.environ", {}, clear=False),
        ):
            mock_client = MagicMock()
            mock_client.complete.return_value = "# plan"
            MockTemplate.return_value = mock_client
            os.environ.pop("OPENAI_API_KEY", None)
            os.environ.pop("ANTHROPIC_API_KEY", None)
            os.environ.pop("GOOGLE_API_KEY", None)
            result = runner.invoke(cli, ["plan", "--memory-map", str(map_file)])
        assert result.exit_code == 0
        MockTemplate.assert_called_once()


def test_main_invokes_cli():
    with patch("playwright_god.cli.cli") as mock_cli:
        main()
    mock_cli.assert_called_once()


# ---------------------------------------------------------------------------
# `playwright-god run` subcommand and `generate --run`
# ---------------------------------------------------------------------------
class TestRunCommand:
    def test_run_help(self, runner):
        result = runner.invoke(cli, ["run", "--help"])
        assert result.exit_code == 0
        assert "SPEC_PATH" in result.output or "spec_path" in result.output.lower()
        assert "--target-dir" in result.output
        assert "--reporter" in result.output
        assert "--artifact-dir" in result.output

    def test_run_passed_exits_zero(self, runner, tmp_path):
        spec = tmp_path / "demo.spec.ts"
        spec.write_text("// noop")
        from playwright_god.runner import RunResult, TestCaseResult

        fake = RunResult(
            status="passed",
            duration_ms=12,
            tests=(TestCaseResult(title="t", status="passed", duration_ms=12),),
            exit_code=0,
            stdout="", stderr="",
            spec_path=spec,
        )
        with patch("playwright_god.cli.PlaywrightRunner") as MockRunner:
            instance = MagicMock()
            instance.run.return_value = fake
            MockRunner.return_value = instance
            result = runner.invoke(cli, ["run", str(spec)])
        assert result.exit_code == 0
        assert "PASS" in result.output or "passed" in result.output.lower()

    def test_run_failed_exits_one(self, runner, tmp_path):
        spec = tmp_path / "demo.spec.ts"
        spec.write_text("// noop")
        from playwright_god.runner import RunResult, TestCaseResult

        fake = RunResult(
            status="failed",
            duration_ms=5,
            tests=(TestCaseResult(title="t", status="failed", duration_ms=5,
                                  error_message="boom"),),
            exit_code=1,
            stdout="", stderr="",
        )
        with patch("playwright_god.cli.PlaywrightRunner") as MockRunner:
            instance = MagicMock()
            instance.run.return_value = fake
            MockRunner.return_value = instance
            result = runner.invoke(cli, ["run", str(spec)])
        assert result.exit_code == 1
        assert "FAIL" in result.output or "boom" in result.output

    def test_run_accepts_directory_spec_path(self, runner, tmp_path):
        spec_dir = tmp_path / "tests"
        spec_dir.mkdir()

        fake = RunResult(
            status="passed",
            duration_ms=0,
            tests=(),
            exit_code=0,
            stdout="",
            stderr="",
            spec_path=spec_dir,
        )
        with patch("playwright_god.cli.PlaywrightRunner") as MockRunner:
            instance = MagicMock()
            instance.run.return_value = fake
            MockRunner.return_value = instance
            result = runner.invoke(cli, ["run", str(spec_dir)])
        assert result.exit_code == 0
        called_arg = instance.run.call_args.args[0]
        assert str(called_arg) == str(spec_dir)

    def test_run_setup_error_exits_two(self, runner, tmp_path):
        spec = tmp_path / "demo.spec.ts"
        spec.write_text("// noop")
        from playwright_god.runner import RunnerSetupError

        with patch("playwright_god.cli.PlaywrightRunner") as MockRunner:
            instance = MagicMock()
            instance.run.side_effect = RunnerSetupError("npx not found")
            MockRunner.return_value = instance
            result = runner.invoke(cli, ["run", str(spec)])
        assert result.exit_code == 2
        assert "npx not found" in result.output

    def test_run_json_output(self, runner, tmp_path):
        spec = tmp_path / "demo.spec.ts"
        spec.write_text("// noop")
        from playwright_god.runner import RunResult

        fake = RunResult(
            status="passed", duration_ms=0, tests=(), exit_code=0,
            stdout="", stderr="", spec_path=spec,
        )
        with patch("playwright_god.cli.PlaywrightRunner") as MockRunner:
            instance = MagicMock()
            instance.run.return_value = fake
            MockRunner.return_value = instance
            result = runner.invoke(cli, ["run", str(spec), "--json"])
        assert result.exit_code == 0
        import json as _json
        parsed = _json.loads(result.output)
        assert parsed["status"] == "passed"
        assert parsed["exit_code"] == 0


class TestGenerateRunFlag:
    def test_generate_run_chains_to_runner(self, runner, tmp_path):
        persist = str(tmp_path / "idx")
        output_file = str(tmp_path / "out.spec.ts")
        from playwright_god.runner import RunResult

        fake = RunResult(
            status="passed", duration_ms=1, tests=(), exit_code=0,
            stdout="", stderr="",
        )
        with (
            patch("playwright_god.cli.DefaultEmbedder") as MockEmb,
            patch("playwright_god.cli.RepositoryIndexer") as MockIdx,
            patch("playwright_god.cli.PlaywrightRunner") as MockRunner,
        ):
            MockEmb.return_value = MagicMock()
            mock_indexer = MagicMock()
            mock_indexer.count.return_value = 0
            mock_indexer.search.return_value = []
            MockIdx.return_value = mock_indexer
            instance = MagicMock()
            instance.run.return_value = fake
            MockRunner.return_value = instance

            os.environ.pop("OPENAI_API_KEY", None)
            result = runner.invoke(
                cli,
                ["generate", "login test", "-d", persist, "-o", output_file, "--run"],
            )
        assert result.exit_code == 0
        instance.run.assert_called_once()
        # The runner was called with the produced spec file path.
        called_arg = instance.run.call_args.args[0]
        assert str(called_arg) == output_file

    def test_generate_run_failure_propagates_exit(self, runner, tmp_path):
        persist = str(tmp_path / "idx")
        output_file = str(tmp_path / "out.spec.ts")
        from playwright_god.runner import RunResult, TestCaseResult

        fake = RunResult(
            status="failed", duration_ms=1,
            tests=(TestCaseResult(title="t", status="failed", duration_ms=1),),
            exit_code=1, stdout="", stderr="",
        )
        with (
            patch("playwright_god.cli.DefaultEmbedder") as MockEmb,
            patch("playwright_god.cli.RepositoryIndexer") as MockIdx,
            patch("playwright_god.cli.PlaywrightRunner") as MockRunner,
        ):
            MockEmb.return_value = MagicMock()
            mock_indexer = MagicMock()
            mock_indexer.count.return_value = 0
            mock_indexer.search.return_value = []
            MockIdx.return_value = mock_indexer
            instance = MagicMock()
            instance.run.return_value = fake
            MockRunner.return_value = instance

            os.environ.pop("OPENAI_API_KEY", None)
            result = runner.invoke(
                cli,
                ["generate", "x", "-d", persist, "-o", output_file, "--run"],
            )
        assert result.exit_code == 1

    def test_generate_run_setup_error_exits_two(self, runner, tmp_path):
        persist = str(tmp_path / "idx")
        output_file = str(tmp_path / "out.spec.ts")
        from playwright_god.runner import RunnerSetupError

        with (
            patch("playwright_god.cli.DefaultEmbedder") as MockEmb,
            patch("playwright_god.cli.RepositoryIndexer") as MockIdx,
            patch("playwright_god.cli.PlaywrightRunner") as MockRunner,
        ):
            MockEmb.return_value = MagicMock()
            mock_indexer = MagicMock()
            mock_indexer.count.return_value = 0
            mock_indexer.search.return_value = []
            MockIdx.return_value = mock_indexer
            instance = MagicMock()
            instance.run.side_effect = RunnerSetupError("@playwright/test missing")
            MockRunner.return_value = instance

            os.environ.pop("OPENAI_API_KEY", None)
            result = runner.invoke(
                cli,
                ["generate", "x", "-d", persist, "-o", output_file, "--run"],
            )
        assert result.exit_code == 2
        assert "@playwright/test missing" in result.output


# ---------------------------------------------------------------------------
# Coverage-aware CLI surface (coverage-aware-planning)
# ---------------------------------------------------------------------------


class TestCoverageReportSubcommand:
    def _sample_payload(self) -> dict:
        return {
            "source": "merged",
            "generated_at": "2026-04-19T00:00:00+00:00",
            "merge_meta": ["frontend", "backend"],
            "totals": {"total_files": 2, "total_lines": 10,
                       "covered_lines": 6, "percent": 60.0},
            "files": {
                "src/a.ts": {"total_lines": 4, "covered_lines": 1, "percent": 25.0,
                             "missing_line_ranges": [[2, 4]]},
                "src/b.py": {"total_lines": 6, "covered_lines": 5, "percent": 83.33,
                             "missing_line_ranges": [[6, 6]]},
            },
        }

    def test_text_format(self, tmp_path):
        from click.testing import CliRunner
        from playwright_god.cli import cli
        import json as _json

        path = tmp_path / "cov.json"
        path.write_text(_json.dumps(self._sample_payload()), encoding="utf-8")
        result = CliRunner().invoke(
            cli, ["coverage", "report", str(path)]
        )
        assert result.exit_code == 0, result.output
        assert "Coverage report" in result.output
        assert "src/a.ts" in result.output
        # Lowest-coverage first
        assert result.output.find("src/a.ts") < result.output.find("src/b.py")

    def test_json_format(self, tmp_path):
        from click.testing import CliRunner
        from playwright_god.cli import cli
        import json as _json

        path = tmp_path / "cov.json"
        path.write_text(_json.dumps(self._sample_payload()), encoding="utf-8")
        result = CliRunner().invoke(
            cli, ["coverage", "report", str(path), "--format", "json"]
        )
        assert result.exit_code == 0
        parsed = _json.loads(result.output)
        assert parsed["source"] == "merged"

    def test_html_format_to_file(self, tmp_path):
        from click.testing import CliRunner
        from playwright_god.cli import cli
        import json as _json

        path = tmp_path / "cov.json"
        out = tmp_path / "cov.html"
        path.write_text(_json.dumps(self._sample_payload()), encoding="utf-8")
        result = CliRunner().invoke(
            cli, ["coverage", "report", str(path), "--format", "html", "-o", str(out)]
        )
        assert result.exit_code == 0
        body = out.read_text(encoding="utf-8")
        assert "<table" in body
        assert "src/a.ts" in body

    def test_invalid_file_exits_nonzero(self, tmp_path):
        from click.testing import CliRunner
        from playwright_god.cli import cli

        bad = tmp_path / "bad.json"
        bad.write_text("not json", encoding="utf-8")
        result = CliRunner().invoke(
            cli, ["coverage", "report", str(bad)]
        )
        assert result.exit_code == 1


class TestPlanPrioritizeFlag:
    def test_plan_accepts_prioritize_and_coverage_report(self, tmp_path, monkeypatch):
        from click.testing import CliRunner
        from playwright_god.cli import cli
        import json as _json

        # Dummy memory map
        mm = tmp_path / "mm.json"
        mm.write_text(_json.dumps({
            "schema_version": "2.1", "total_files": 0, "total_chunks": 0,
            "languages": {}, "files": [],
        }), encoding="utf-8")
        # Dummy coverage report
        cov = tmp_path / "cov.json"
        cov.write_text(_json.dumps({
            "source": "merged", "files": {
                "x.py": {"total_lines": 4, "covered_lines": 1, "percent": 25.0,
                         "missing_line_ranges": [[2, 4]]},
            }
        }), encoding="utf-8")

        # Force template provider so no network is needed.
        monkeypatch.setenv("PLAYWRIGHT_GOD_PROVIDER", "template")
        result = CliRunner().invoke(
            cli,
            [
                "plan",
                "--memory-map", str(mm),
                "--coverage-report", str(cov),
                "--prioritize", "percent",
            ],
        )
        assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# CLI helpers (coverage-aware-planning internals)
# ---------------------------------------------------------------------------


class TestBuildUncoveredExcerpts:
    def test_reads_files_and_caps(self, tmp_path):
        from playwright_god.cli import _build_uncovered_excerpts
        from playwright_god.coverage import FileCoverage, CoverageReport

        src = tmp_path / "a.py"
        src.write_text("\n".join(f"line {i}" for i in range(1, 11)), encoding="utf-8")
        fc = FileCoverage(
            path="a.py", total_lines=10, covered_lines=2,
            missing_line_ranges=((3, 5), (7, 8)),
        )
        rep = CoverageReport(source="backend", files={"a.py": fc}, generated_at="t")
        out = _build_uncovered_excerpts(rep, cap=10, workdir=tmp_path)
        assert len(out) == 2
        assert out[0][0] == "a.py"
        assert "line 3" in out[0][3]

    def test_skips_missing_files(self, tmp_path):
        from playwright_god.cli import _build_uncovered_excerpts
        from playwright_god.coverage import FileCoverage, CoverageReport

        fc = FileCoverage(
            path="missing.py", total_lines=4, covered_lines=0,
            missing_line_ranges=((1, 4),),
        )
        rep = CoverageReport(source="backend", files={"missing.py": fc}, generated_at="t")
        assert _build_uncovered_excerpts(rep, workdir=tmp_path) == []

    def test_cap_zero_returns_nothing(self, tmp_path):
        from playwright_god.cli import _build_uncovered_excerpts
        from playwright_god.coverage import FileCoverage, CoverageReport

        src = tmp_path / "a.py"
        src.write_text("a\nb\nc\n", encoding="utf-8")
        fc = FileCoverage(path="a.py", total_lines=3, covered_lines=0,
                          missing_line_ranges=((1, 3),))
        rep = CoverageReport(source="backend", files={"a.py": fc}, generated_at="t")
        out = _build_uncovered_excerpts(rep, cap=0, workdir=tmp_path)
        assert out == []


class TestRenderCoverage:
    def _payload(self) -> dict:
        return {
            "source": "backend",
            "generated_at": "t",
            "totals": {"total_files": 1, "total_lines": 10, "covered_lines": 4, "percent": 40.0},
            "files": {
                "a.py": {"total_lines": 10, "covered_lines": 4, "percent": 40.0,
                         "missing_line_ranges": [[1, 1], [3, 4], [6, 6], [8, 8],
                                                  [10, 10], [12, 12], [14, 14], [16, 16]]},
                "broken": "ignored",
            },
        }

    def test_text_truncates_missing_ranges(self):
        from playwright_god.cli import _render_coverage_text
        out = _render_coverage_text(self._payload())
        assert "more" in out  # +2 more truncation marker
        assert "a.py" in out

    def test_html_skips_invalid(self):
        from playwright_god.cli import _render_coverage_html
        out = _render_coverage_html(self._payload())
        assert "<table" in out
        assert "a.py" in out


class TestGenerateWithCoverageReport:
    def test_loads_excerpts_and_runs(self, tmp_path, monkeypatch):
        from click.testing import CliRunner
        from playwright_god.cli import cli
        import json as _json

        # Source file referenced by the coverage report.
        src = tmp_path / "src" / "a.py"
        src.parent.mkdir(parents=True)
        src.write_text("line1\nline2\nline3\n", encoding="utf-8")

        cov_report = tmp_path / "cov.json"
        cov_report.write_text(_json.dumps({
            "source": "backend",
            "generated_at": "t",
            "files": {
                "src/a.py": {"total_lines": 3, "covered_lines": 1,
                             "missing_line_ranges": [[2, 3]]},
            },
        }), encoding="utf-8")

        out = tmp_path / "out.spec.ts"
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("PLAYWRIGHT_GOD_PROVIDER", "template")
        result = CliRunner().invoke(
            cli,
            [
                "generate", "scenario X",
                "--persist-dir", str(tmp_path / ".idx"),
                "--coverage-report", str(cov_report),
                "--coverage-cap", "5",
                "-o", str(out),
            ],
        )
        assert result.exit_code == 0, result.output
        assert out.is_file()

    def test_invalid_coverage_report_warns(self, tmp_path, monkeypatch):
        from click.testing import CliRunner
        from playwright_god.cli import cli

        bad = tmp_path / "cov.json"
        bad.write_text("not json", encoding="utf-8")
        monkeypatch.setenv("PLAYWRIGHT_GOD_PROVIDER", "template")
        result = CliRunner().invoke(
            cli,
            [
                "generate", "x",
                "--persist-dir", str(tmp_path / ".idx"),
                "--coverage-report", str(bad),
                "-o", str(tmp_path / "out.ts"),
            ],
        )
        assert result.exit_code == 0
        assert "could not load --coverage-report" in result.output


class TestRunCommandCoverageFlag:
    def test_run_with_coverage_flag(self, tmp_path, monkeypatch):
        from click.testing import CliRunner
        from playwright_god.cli import cli
        import playwright_god.runner as runner_mod

        # Stub a Playwright project + spec.
        target = tmp_path / "app"
        target.mkdir()
        (target / "package.json").write_text(
            '{"devDependencies": {"@playwright/test": "1"}}', encoding="utf-8"
        )
        spec = target / "x.spec.ts"
        spec.write_text("// noop", encoding="utf-8")

        monkeypatch.setattr(runner_mod, "_which", lambda c: "/usr/bin/npx")

        def fake_run(cmd, **kw):
            env = kw.get("env") or {}
            report_path = env.get("PLAYWRIGHT_JSON_OUTPUT_NAME")
            if report_path:
                from pathlib import Path as _P
                _P(report_path).parent.mkdir(parents=True, exist_ok=True)
                _P(report_path).write_text("{}", encoding="utf-8")
            import subprocess as _sp
            return _sp.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(runner_mod.subprocess, "run", fake_run)

        result = CliRunner().invoke(
            cli, ["run", str(spec), "--target-dir", str(target), "--coverage"]
        )
        assert result.exit_code == 0, result.output

    def test_run_setup_error_exits_2(self, tmp_path, monkeypatch):
        from click.testing import CliRunner
        from playwright_god.cli import cli
        import playwright_god.runner as runner_mod

        target = tmp_path / "app"
        target.mkdir()
        spec = target / "x.spec.ts"
        spec.write_text("// noop", encoding="utf-8")
        monkeypatch.setattr(runner_mod, "_which", lambda c: None)
        result = CliRunner().invoke(
            cli, ["run", str(spec), "--target-dir", str(target)]
        )
        assert result.exit_code == 2


class TestGenerateRunFlag:
    def _stub_runner(self, monkeypatch, target):
        import playwright_god.runner as runner_mod

        monkeypatch.setattr(runner_mod, "_which", lambda c: "/usr/bin/npx")

        def fake_run(cmd, **kw):
            env = kw.get("env") or {}
            rp = env.get("PLAYWRIGHT_JSON_OUTPUT_NAME")
            if rp:
                from pathlib import Path as _P
                _P(rp).parent.mkdir(parents=True, exist_ok=True)
                _P(rp).write_text("{}", encoding="utf-8")
            import subprocess as _sp
            return _sp.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(runner_mod.subprocess, "run", fake_run)

    def _make_target(self, tmp_path):
        target = tmp_path / "app"
        target.mkdir()
        (target / "package.json").write_text(
            '{"devDependencies":{"@playwright/test":"1"}}', encoding="utf-8"
        )
        return target

    def test_generate_run_writes_temp_spec(self, tmp_path, monkeypatch):
        from click.testing import CliRunner
        from playwright_god.cli import cli

        target = self._make_target(tmp_path)
        self._stub_runner(monkeypatch, target)
        monkeypatch.setenv("PLAYWRIGHT_GOD_PROVIDER", "template")
        result = CliRunner().invoke(
            cli,
            [
                "generate", "scenario",
                "--persist-dir", str(tmp_path / ".idx"),
                "--run", "--target-dir", str(target),
            ],
        )
        # Exit 0 (passed) since fake_run returns success and tests are empty.
        assert result.exit_code == 0, result.output
        assert "Wrote temp spec to" in result.output

    def test_generate_run_with_backend_coverage(self, tmp_path, monkeypatch):
        from click.testing import CliRunner
        from playwright_god.cli import cli
        import playwright_god.coverage as cov_mod

        target = self._make_target(tmp_path)
        self._stub_runner(monkeypatch, target)
        monkeypatch.setenv("PLAYWRIGHT_GOD_PROVIDER", "template")

        # Stub the backend collector to avoid any subprocess.
        class FakeCollector:
            def __init__(self, **kw):
                pass

            def collect(self, run_callable, **kw):
                run_callable()
                return cov_mod.merge(
                    cov_mod.CoverageReport(source="frontend", files={}, generated_at="t"),
                    cov_mod.CoverageReport(source="backend", files={}, generated_at="t"),
                )

        monkeypatch.setattr("playwright_god.cli.CoverageCollector", FakeCollector, raising=False)
        # Direct import path inside generate uses `from .coverage import CoverageCollector`.
        monkeypatch.setattr(cov_mod, "CoverageCollector", FakeCollector)

        out = tmp_path / "out.spec.ts"
        result = CliRunner().invoke(
            cli,
            [
                "generate", "scenario",
                "--persist-dir", str(tmp_path / ".idx"),
                "--run", "--target-dir", str(target),
                "-o", str(out),
                "--backend-coverage", "echo backend",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Coverage report:" in result.output

    def test_generate_run_setup_error(self, tmp_path, monkeypatch):
        from click.testing import CliRunner
        from playwright_god.cli import cli
        import playwright_god.runner as runner_mod

        target = self._make_target(tmp_path)
        monkeypatch.setattr(runner_mod, "_which", lambda c: None)
        monkeypatch.setenv("PLAYWRIGHT_GOD_PROVIDER", "template")
        out = tmp_path / "out.spec.ts"
        result = CliRunner().invoke(
            cli,
            [
                "generate", "scenario",
                "--persist-dir", str(tmp_path / ".idx"),
                "--run", "--target-dir", str(target), "-o", str(out),
            ],
        )
        assert result.exit_code == 2


class TestPlanCoverageReportWarn:
    def test_unparseable_coverage_report_warns(self, tmp_path, monkeypatch):
        from click.testing import CliRunner
        from playwright_god.cli import cli

        bad = tmp_path / "cov.json"
        bad.write_text("not json", encoding="utf-8")
        mm = tmp_path / "mm.json"
        mm.write_text(
            '{"schema_version":"2.1","total_files":0,"total_chunks":0,'
            '"languages":{},"files":[]}', encoding="utf-8"
        )
        monkeypatch.setenv("PLAYWRIGHT_GOD_PROVIDER", "template")
        result = CliRunner().invoke(
            cli, ["plan", "--memory-map", str(mm), "--coverage-report", str(bad)]
        )
        assert result.exit_code == 0
        assert "could not load --coverage-report" in result.output


class TestRunBackendCoverage:
    def test_run_with_backend_coverage(self, tmp_path, monkeypatch):
        from click.testing import CliRunner
        from playwright_god.cli import cli
        import playwright_god.runner as runner_mod
        import playwright_god.coverage as cov_mod

        target = tmp_path / "app"
        target.mkdir()
        (target / "package.json").write_text(
            '{"devDependencies":{"@playwright/test":"1"}}', encoding="utf-8"
        )
        spec = target / "x.spec.ts"
        spec.write_text("// noop", encoding="utf-8")

        monkeypatch.setattr(runner_mod, "_which", lambda c: "/usr/bin/npx")

        def fake_run(cmd, **kw):
            env = kw.get("env") or {}
            rp = env.get("PLAYWRIGHT_JSON_OUTPUT_NAME")
            if rp:
                from pathlib import Path as _P
                _P(rp).parent.mkdir(parents=True, exist_ok=True)
                _P(rp).write_text("{}", encoding="utf-8")
            import subprocess as _sp
            return _sp.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(runner_mod.subprocess, "run", fake_run)

        class FakeCollector:
            def __init__(self, **kw):
                pass

            def collect(self, run_callable, **kw):
                run_callable()
                return cov_mod.merge(
                    cov_mod.CoverageReport(source="frontend", files={}, generated_at="t"),
                    cov_mod.CoverageReport(source="backend", files={}, generated_at="t"),
                )

        monkeypatch.setattr(cov_mod, "CoverageCollector", FakeCollector)

        result = CliRunner().invoke(
            cli,
            [
                "run", str(spec),
                "--target-dir", str(target),
                "--backend-coverage", "echo backend",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Coverage report:" in result.output


class TestCoveragePayloadForPlan:
    def test_skips_invalid_entries(self):
        from playwright_god.cli import _coverage_payload_for_plan
        out = _coverage_payload_for_plan({"files": {"a": "broken",
                                                     "b": {"total_lines": 0, "covered_lines": 0}}})
        assert out["summary"]["files"] == 1
        # Default percent path: total=0 → 100.0
        assert out["files"][0]["percent"] == 100.0


# ---------------------------------------------------------------------------
# `refine` subcommand (iterative-refinement Task 5.7)
# ---------------------------------------------------------------------------


class TestRefineCommand:
    def _patch(self, monkeypatch, tmp_path, *, outcomes=("passed",)):
        """Install scripted generator + runner so the loop is hermetic."""
        from click.testing import CliRunner
        from playwright_god import cli as cli_mod
        from playwright_god import refinement as ref_mod
        from playwright_god.runner import RunResult, TestCaseResult

        def _result_for(outcome: str) -> RunResult:
            if outcome == "passed":
                return RunResult(
                    status="passed",
                    duration_ms=1,
                    tests=(TestCaseResult(title="t", status="passed", duration_ms=1),),
                    exit_code=0,
                    stdout="",
                    stderr="",
                )
            if outcome == "compile_failed":
                return RunResult(
                    status="error",
                    duration_ms=0,
                    tests=(),
                    exit_code=1,
                    stdout="",
                    stderr="src/x.spec.ts(1,2): error TS2304: nope",
                )
            return RunResult(
                status="failed",
                duration_ms=1,
                tests=(
                    TestCaseResult(
                        title="t",
                        status="failed",
                        duration_ms=1,
                        error_message="boom",
                    ),
                ),
                exit_code=1,
                stdout="",
                stderr="",
            )

        results = [_result_for(o) for o in outcomes]

        class _StubRunner:
            def __init__(self, *a, **kw):
                self._idx = 0

            def run(self, spec_path):
                idx = min(self._idx, len(results) - 1)
                self._idx += 1
                return results[idx]

        class _StubGenerator:
            def __init__(self, *a, **kw):
                self._n = 0

            def generate(self, description, **kwargs):
                self._n += 1
                return f"// attempt {self._n}\n"

        class _StubIndexer:
            def __init__(self, *a, **kw):
                pass

            def count(self):
                return 0

            def search(self, *a, **kw):
                return []

        monkeypatch.setattr(cli_mod, "PlaywrightRunner", _StubRunner)
        monkeypatch.setattr(cli_mod, "PlaywrightTestGenerator", _StubGenerator)
        monkeypatch.setattr(cli_mod, "RepositoryIndexer", _StubIndexer)
        return CliRunner()

    def test_refine_default_stops_on_first_pass_exit_zero(
        self, tmp_path, monkeypatch
    ):
        from playwright_god.cli import cli

        runner = self._patch(monkeypatch, tmp_path, outcomes=("passed",))
        out = tmp_path / "spec.spec.ts"
        result = runner.invoke(
            cli,
            [
                "refine",
                "login flow",
                "-o",
                str(out),
                "--mock-embedder",
                "--max-attempts",
                "3",
            ],
        )
        assert result.exit_code == 0, result.output
        assert out.exists()
        assert "1 attempt" in result.output

    def test_refine_failure_returns_nonzero_exit(self, tmp_path, monkeypatch):
        from playwright_god.cli import cli

        runner = self._patch(
            monkeypatch, tmp_path, outcomes=("runtime_failed",) * 3
        )
        out = tmp_path / "spec.spec.ts"
        result = runner.invoke(
            cli,
            [
                "refine",
                "login",
                "-o",
                str(out),
                "--mock-embedder",
                "--max-attempts",
                "3",
            ],
        )
        assert result.exit_code != 0
        assert "3 attempt" in result.output

    def test_refine_warns_when_max_attempts_above_5(self, tmp_path, monkeypatch):
        from playwright_god.cli import cli

        runner = self._patch(monkeypatch, tmp_path, outcomes=("passed",))
        out = tmp_path / "spec.spec.ts"
        result = runner.invoke(
            cli,
            [
                "refine",
                "x",
                "-o",
                str(out),
                "--mock-embedder",
                "--max-attempts",
                "7",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "high attempt cap" in result.output

    def test_refine_rejects_max_attempts_above_hard_cap(
        self, tmp_path, monkeypatch
    ):
        from playwright_god.cli import cli

        runner = self._patch(monkeypatch, tmp_path, outcomes=("passed",))
        out = tmp_path / "spec.spec.ts"
        result = runner.invoke(
            cli,
            [
                "refine",
                "x",
                "-o",
                str(out),
                "--mock-embedder",
                "--max-attempts",
                "12",
            ],
        )
        assert result.exit_code == 2
        assert "hard cap" in result.output

    def test_refine_writes_audit_log_when_artifact_dir_set(
        self, tmp_path, monkeypatch
    ):
        from playwright_god.cli import cli

        runner = self._patch(
            monkeypatch, tmp_path, outcomes=("runtime_failed", "passed")
        )
        out = tmp_path / "spec.spec.ts"
        artifacts = tmp_path / "artifacts"
        result = runner.invoke(
            cli,
            [
                "refine",
                "x",
                "-o",
                str(out),
                "--mock-embedder",
                "--max-attempts",
                "2",
                "--artifact-dir",
                str(artifacts),
            ],
        )
        assert result.exit_code == 0, result.output
        # Find the JSONL log under artifacts/runs/<ts>/refinement_log.jsonl
        logs = list(artifacts.glob("runs/*/refinement_log.jsonl"))
        assert logs, "expected a refinement audit log to be written"
        lines = logs[0].read_text().splitlines()
        assert len(lines) == 2

    def test_refine_help_lists_flags(self):
        from click.testing import CliRunner
        from playwright_god.cli import cli

        result = CliRunner().invoke(cli, ["refine", "--help"])
        assert result.exit_code == 0
        for flag in ("--max-attempts", "--stop-on", "--coverage-target", "--retry-on-flake"):
            assert flag in result.output


    def test_refine_provider_branches(self, tmp_path, monkeypatch):
        """Cover openai/anthropic/gemini/ollama provider construction paths."""
        from unittest.mock import patch
        from playwright_god.cli import cli
        from click.testing import CliRunner

        for prov, mock_target in [
            ("openai", "playwright_god.cli.OpenAIClient"),
            ("anthropic", "playwright_god.cli.AnthropicClient"),
            ("gemini", "playwright_god.cli.GeminiClient"),
            ("ollama", "playwright_god.cli.OllamaClient"),
        ]:
            runner = self._patch(monkeypatch, tmp_path, outcomes=("passed",))
            out = tmp_path / f"spec_{prov}.spec.ts"
            with patch(mock_target) as MockClient:
                MockClient.return_value = object()  # not actually used by stub generator
                result = runner.invoke(
                    cli,
                    [
                        "refine",
                        "x",
                        "-o",
                        str(out),
                        "--mock-embedder",
                        "--max-attempts",
                        "1",
                        "--provider",
                        prov,
                        "--api-key",
                        "fake",
                    ],
                )
            assert result.exit_code == 0, (prov, result.output)
            MockClient.assert_called_once()

    def test_refine_warns_on_invalid_memory_map(self, tmp_path, monkeypatch):
        """Memory-map load failure path is warned-on, not fatal."""
        from playwright_god.cli import cli

        runner = self._patch(monkeypatch, tmp_path, outcomes=("passed",))
        out = tmp_path / "s.spec.ts"
        bad_map = tmp_path / "bogus.json"
        bad_map.write_text("not json at all{")
        result = runner.invoke(
            cli,
            [
                "refine",
                "x",
                "-o",
                str(out),
                "--mock-embedder",
                "--max-attempts",
                "1",
                "--memory-map",
                str(bad_map),
            ],
        )
        # Should still succeed; warning is on stderr (mixed into result.output by click runner).
        assert result.exit_code == 0, result.output
        assert "could not load --memory-map" in result.output


# ---------------------------------------------------------------------------
# `graph extract` subcommand (flow-graph-extraction)
# ---------------------------------------------------------------------------


class TestGraphExtractCLI:
    def _write_app(self, root: Path) -> None:
        (root / "api.py").write_text(
            "from fastapi import FastAPI\n"
            "app = FastAPI()\n"
            "@app.get('/healthz')\n"
            "def hz():\n"
            "    return 'ok'\n",
            encoding="utf-8",
        )

    def test_extract_writes_default_path(self, runner, tmp_path):
        self._write_app(tmp_path)
        persist = tmp_path / "_pg"
        result = runner.invoke(
            cli,
            ["graph", "extract", str(tmp_path), "--persist-dir", str(persist)],
        )
        assert result.exit_code == 0, result.output
        out = persist / "flow_graph.json"
        assert out.is_file()
        assert "1 routes" in result.output
        import json
        data = json.loads(out.read_text(encoding="utf-8"))
        assert any(n["id"] == "route:GET:/healthz" for n in data["nodes"])

    def test_extract_explicit_output(self, runner, tmp_path):
        self._write_app(tmp_path)
        out = tmp_path / "graph.json"
        result = runner.invoke(
            cli, ["graph", "extract", str(tmp_path), "-o", str(out)]
        )
        assert result.exit_code == 0
        assert out.is_file()

    def test_check_passes_when_no_drift(self, runner, tmp_path):
        self._write_app(tmp_path)
        persist = tmp_path / "_pg"
        first = runner.invoke(
            cli, ["graph", "extract", str(tmp_path), "--persist-dir", str(persist)]
        )
        assert first.exit_code == 0
        result = runner.invoke(
            cli,
            ["graph", "extract", str(tmp_path), "--persist-dir", str(persist), "--check"],
        )
        assert result.exit_code == 0
        assert "up to date" in result.output

    def test_check_fails_on_drift(self, runner, tmp_path):
        self._write_app(tmp_path)
        persist = tmp_path / "_pg"
        runner.invoke(
            cli, ["graph", "extract", str(tmp_path), "--persist-dir", str(persist)]
        )
        # Add a new route to introduce drift
        (tmp_path / "api2.py").write_text(
            "from fastapi import FastAPI\n"
            "app = FastAPI()\n"
            "@app.post('/items')\n"
            "def items():\n"
            "    return {}\n",
            encoding="utf-8",
        )
        result = runner.invoke(
            cli,
            ["graph", "extract", str(tmp_path), "--persist-dir", str(persist), "--check"],
        )
        assert result.exit_code == 1
        assert "drift detected" in result.output
        assert "+route:POST:/items" in result.output

    def test_check_without_persisted_graph_errors(self, runner, tmp_path):
        self._write_app(tmp_path)
        result = runner.invoke(
            cli,
            ["graph", "extract", str(tmp_path),
             "--persist-dir", str(tmp_path / "missing"), "--check"],
        )
        assert result.exit_code == 2
        assert "requires an existing graph" in result.output

    def test_plan_with_prioritize_routes(self, runner, tmp_path, monkeypatch):
        # Build minimal index
        (tmp_path / "api.py").write_text(
            "from fastapi import FastAPI\n"
            "app = FastAPI()\n"
            "@app.get('/x')\n"
            "def x():\n    return 'ok'\n",
            encoding="utf-8",
        )
        # Index
        idx = runner.invoke(
            cli,
            ["index", str(tmp_path), "-d", str(tmp_path / "_idx"), "--mock-embedder"],
        )
        assert idx.exit_code == 0, idx.output
        # Build flow graph
        gout = tmp_path / "g.json"
        runner.invoke(cli, ["graph", "extract", str(tmp_path), "-o", str(gout)])
        # Build a coverage report json so plan accepts --coverage-report
        cov_path = tmp_path / "cov.json"
        cov_path.write_text(
            '{"source":"merged","files":{"api.py":{"total_lines":5,'
            '"covered_lines":2,"percent":40.0,"missing_line_ranges":[[3,5]]}},'
            '"routes":{"total":1,"covered":[],"uncovered":["route:GET:/x"]}}',
            encoding="utf-8",
        )
        plan_out = tmp_path / "plan.md"
        result = runner.invoke(
            cli,
            [
                "plan",
                "-d", str(tmp_path / "_idx"),
                "--coverage-report", str(cov_path),
                "--prioritize", "routes",
                "--flow-graph", str(gout),
                "-o", str(plan_out),
            ],
        )
        assert result.exit_code == 0, result.output
        assert plan_out.is_file()


# ---------------------------------------------------------------------------
# Coverage report rendering with routes block
# ---------------------------------------------------------------------------


class TestCoverageReportRoutes:
    def _payload(self) -> dict:
        return {
            "source": "merged",
            "generated_at": "t",
            "totals": {"total_files": 1, "total_lines": 5, "covered_lines": 3, "percent": 60.0},
            "files": {"a.py": {"total_lines": 5, "covered_lines": 3, "percent": 60.0,
                               "missing_line_ranges": [[4, 5]]}},
            "routes": {
                "total": 2,
                "covered": ["route:GET:/a"],
                "uncovered": ["route:POST:/b"],
            },
        }

    def test_text_format_includes_routes(self, runner, tmp_path):
        import json as _json
        p = tmp_path / "cov.json"
        p.write_text(_json.dumps(self._payload()), encoding="utf-8")
        result = runner.invoke(cli, ["coverage", "report", str(p), "--format", "text"])
        assert result.exit_code == 0, result.output
        assert "Routes" in result.output
        assert "route:POST:/b" in result.output

    def test_html_format_includes_routes(self, runner, tmp_path):
        import json as _json
        p = tmp_path / "cov.json"
        p.write_text(_json.dumps(self._payload()), encoding="utf-8")
        result = runner.invoke(cli, ["coverage", "report", str(p), "--format", "html"])
        assert result.exit_code == 0
        assert "<h2>Routes" in result.output
        assert "route:POST:/b" in result.output

    def test_text_format_truncates_many_uncovered(self, runner, tmp_path):
        import json as _json
        payload = self._payload()
        payload["routes"]["uncovered"] = [f"route:GET:/p{i}" for i in range(40)]
        payload["routes"]["total"] = 41
        p = tmp_path / "cov.json"
        p.write_text(_json.dumps(payload), encoding="utf-8")
        result = runner.invoke(cli, ["coverage", "report", str(p), "--format", "text"])
        assert "more uncovered" in result.output

    def test_routes_html_returns_empty_when_no_routes(self):
        from playwright_god.cli import _render_coverage_routes_html
        assert _render_coverage_routes_html({}) == ""


def test_load_flow_graph_handles_invalid_json(runner, tmp_path):
    from playwright_god.cli import _load_flow_graph

    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        _load_flow_graph(str(p))
    assert exc.value.code == 1


def test_load_flow_graph_succeeds_for_valid_payload(tmp_path):
    from playwright_god.cli import _load_flow_graph
    from playwright_god.flow_graph import FlowGraph, Route

    g = FlowGraph.from_iterables([Route(method="GET", path="/x")])
    p = tmp_path / "g.json"
    p.write_text(g.to_json(), encoding="utf-8")
    loaded = _load_flow_graph(str(p))
    assert any(n.id == "route:GET:/x" for n in loaded.nodes)


def test_graph_extract_check_with_corrupt_persisted(runner, tmp_path):
    persist = tmp_path / "_pg"
    persist.mkdir()
    (persist / "flow_graph.json").write_text("not json", encoding="utf-8")
    (tmp_path / "x.py").write_text("\n", encoding="utf-8")
    result = runner.invoke(
        cli, ["graph", "extract", str(tmp_path),
              "--persist-dir", str(persist), "--check"],
    )
    assert result.exit_code == 2
    assert "could not load" in result.output


# ---------------------------------------------------------------------------
# Update command tests
# ---------------------------------------------------------------------------


class TestUpdateCommand:
    """Tests for the `update` CLI command."""

    def test_update_help(self, runner):
        result = runner.invoke(cli, ["update", "--help"])
        assert result.exit_code == 0
        assert "--spec-dir" in result.output
        assert "--dry-run" in result.output
        assert "--strict-update" in result.output
        assert "--allow-dirty" in result.output

    def test_update_dry_run_shows_plan(self, runner, tmp_path):
        """--dry-run prints the plan without executing."""
        from playwright_god.flow_graph import FlowGraph, Route

        # Setup
        spec_dir = tmp_path / "specs"
        spec_dir.mkdir()
        persist_dir = tmp_path / "persist"
        persist_dir.mkdir()

        # Create flow graph with routes
        fg = FlowGraph.from_iterables(
            nodes=[
                Route(method="GET", path="/"),
                Route(method="GET", path="/login"),
            ]
        )
        fg_path = persist_dir / "flow_graph.json"
        fg_path.write_text(fg.to_json(), encoding="utf-8")

        # Create a spec covering one node
        (spec_dir / "home.spec.ts").write_text(
            '// @pg-tags route:GET:/\ntest("home", async () => {});',
            encoding="utf-8",
        )

        result = runner.invoke(
            cli,
            [
                "update",
                "--spec-dir", str(spec_dir),
                "--persist-dir", str(persist_dir),
                "--flow-graph", str(fg_path),
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert "--dry-run" in result.output
        assert "add:" in result.output
        assert "keep:" in result.output

    def test_update_saves_plan_json(self, runner, tmp_path):
        """Update saves update_plan.json to persist dir."""
        from playwright_god.flow_graph import FlowGraph, Route

        spec_dir = tmp_path / "specs"
        spec_dir.mkdir()
        persist_dir = tmp_path / "persist"

        fg = FlowGraph.from_iterables(nodes=[Route(method="GET", path="/")])
        fg_path = tmp_path / "flow_graph.json"
        fg_path.write_text(fg.to_json(), encoding="utf-8")

        result = runner.invoke(
            cli,
            [
                "update",
                "--spec-dir", str(spec_dir),
                "--persist-dir", str(persist_dir),
                "--flow-graph", str(fg_path),
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        plan_path = persist_dir / "update_plan.json"
        assert plan_path.exists()
        # Verify it's valid JSON
        import json
        data = json.loads(plan_path.read_text())
        assert "add" in data
        assert "summary" in data

    def test_update_refuses_dirty_tree_by_default(self, runner, tmp_path):
        """Update refuses to run if spec files have unstaged changes."""
        from playwright_god.flow_graph import FlowGraph, Route

        spec_dir = tmp_path / "specs"
        spec_dir.mkdir()
        persist_dir = tmp_path / "persist"

        fg = FlowGraph.from_iterables(nodes=[Route(method="GET", path="/")])
        fg_path = tmp_path / "flow_graph.json"
        fg_path.write_text(fg.to_json(), encoding="utf-8")

        with patch("playwright_god.cli._check_dirty_specs") as mock_check:
            mock_check.return_value = ["specs/dirty.spec.ts"]

            result = runner.invoke(
                cli,
                [
                    "update",
                    "--spec-dir", str(spec_dir),
                    "--persist-dir", str(persist_dir),
                    "--flow-graph", str(fg_path),
                ],
            )

        assert result.exit_code != 0
        assert "Dirty" in result.output or "unstaged" in result.output

    def test_update_allow_dirty_bypasses_check(self, runner, tmp_path):
        """--allow-dirty bypasses the dirty tree check."""
        from playwright_god.flow_graph import FlowGraph, Route

        spec_dir = tmp_path / "specs"
        spec_dir.mkdir()
        persist_dir = tmp_path / "persist"

        fg = FlowGraph.from_iterables(nodes=[Route(method="GET", path="/")])
        fg_path = tmp_path / "flow_graph.json"
        fg_path.write_text(fg.to_json(), encoding="utf-8")

        with patch("playwright_god.cli._check_dirty_specs") as mock_check:
            mock_check.return_value = ["specs/dirty.spec.ts"]

            result = runner.invoke(
                cli,
                [
                    "update",
                    "--spec-dir", str(spec_dir),
                    "--persist-dir", str(persist_dir),
                    "--flow-graph", str(fg_path),
                    "--allow-dirty",
                    "--dry-run",
                ],
            )

        # Should succeed despite dirty files
        assert result.exit_code == 0

    def test_update_extracts_graph_when_not_provided(self, runner, tmp_path):
        """Update extracts flow graph from cwd if not provided."""
        from playwright_god.flow_graph import FlowGraph, Route

        spec_dir = tmp_path / "specs"
        spec_dir.mkdir()
        persist_dir = tmp_path / "persist"

        mock_fg = FlowGraph.from_iterables(nodes=[Route(method="GET", path="/")])

        with (
            patch("playwright_god.cli._check_dirty_specs", return_value=[]),
            patch("playwright_god.extractors.extract", return_value=mock_fg),
        ):
            result = runner.invoke(
                cli,
                [
                    "update",
                    "--spec-dir", str(spec_dir),
                    "--persist-dir", str(persist_dir),
                    "--dry-run",
                ],
            )

        assert result.exit_code == 0
        assert "Extracting flow graph" in result.output

    def test_update_loads_prior_outcomes(self, runner, tmp_path):
        """Update loads prior outcomes when artifact-dir is provided."""
        import json

        from playwright_god.flow_graph import FlowGraph, Route

        spec_dir = tmp_path / "specs"
        spec_dir.mkdir()
        persist_dir = tmp_path / "persist"
        artifact_dir = tmp_path / "artifacts"

        fg = FlowGraph.from_iterables(nodes=[Route(method="GET", path="/")])
        fg_path = tmp_path / "flow_graph.json"
        fg_path.write_text(fg.to_json(), encoding="utf-8")

        # Create spec
        spec_file = spec_dir / "home.spec.ts"
        spec_file.write_text(
            '// @pg-tags route:GET:/\ntest("home", async () => {});',
            encoding="utf-8",
        )

        # Create runs with report
        runs_dir = artifact_dir / "runs" / "2024-01-15"
        runs_dir.mkdir(parents=True)
        report = {
            "suites": [
                {"specs": [{"file": str(spec_file), "tests": [{"status": "failed"}]}]}
            ]
        }
        (runs_dir / "report.json").write_text(json.dumps(report), encoding="utf-8")

        result = runner.invoke(
            cli,
            [
                "update",
                "--spec-dir", str(spec_dir),
                "--persist-dir", str(persist_dir),
                "--flow-graph", str(fg_path),
                "--artifact-dir", str(artifact_dir),
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert "prior run outcomes" in result.output

    def test_update_nothing_to_do(self, runner, tmp_path):
        """Update reports nothing to do when all specs are up-to-date."""
        from playwright_god.flow_graph import FlowGraph, Route

        spec_dir = tmp_path / "specs"
        spec_dir.mkdir()
        persist_dir = tmp_path / "persist"

        fg = FlowGraph.from_iterables(nodes=[Route(method="GET", path="/")])
        fg_path = tmp_path / "flow_graph.json"
        fg_path.write_text(fg.to_json(), encoding="utf-8")

        # Spec covers the node (via @pg-tags)
        spec_file = spec_dir / "home.spec.ts"
        spec_file.write_text(
            '// @pg-tags route:GET:/\ntest("home", async () => {});',
            encoding="utf-8",
        )

        result = runner.invoke(
            cli,
            [
                "update",
                "--spec-dir", str(spec_dir),
                "--persist-dir", str(persist_dir),
                "--flow-graph", str(fg_path),
                "--dry-run",  # Use dry-run mode - simpler test
            ],
        )

        assert result.exit_code == 0
        # With proper tags, the spec should be in 'keep' bucket
        assert "keep:" in result.output
        # Verify plan summary is output
        assert "Update Plan Summary" in result.output

    def test_update_empty_plan_no_dry_run(self, runner, tmp_path):
        """When plan is empty (all keep), non-dry-run says nothing to do."""
        from playwright_god.flow_graph import FlowGraph, Route

        spec_dir = tmp_path / "specs"
        spec_dir.mkdir()
        persist_dir = tmp_path / "persist"

        fg = FlowGraph.from_iterables(nodes=[Route(method="GET", path="/")])
        fg_path = tmp_path / "flow_graph.json"
        fg_path.write_text(fg.to_json(), encoding="utf-8")

        # Spec covers the node (via @pg-tags)
        spec_file = spec_dir / "home.spec.ts"
        spec_file.write_text(
            '// @pg-tags route:GET:/\ntest("home", async () => {});',
            encoding="utf-8",
        )

        result = runner.invoke(
            cli,
            [
                "update",
                "--spec-dir", str(spec_dir),
                "--persist-dir", str(persist_dir),
                "--flow-graph", str(fg_path),
                "--allow-dirty",  # Skip git check since tmp_path is not a git repo
            ],
        )

        assert result.exit_code == 0
        # Should see "Nothing to do" message
        assert "Nothing to do" in result.output


class TestCheckDirtySpecs:
    """Tests for _check_dirty_specs helper."""

    def test_returns_empty_when_not_git_repo(self, tmp_path):
        from playwright_god.cli import _check_dirty_specs

        # tmp_path is not a git repo
        spec_dir = tmp_path / "specs"
        spec_dir.mkdir()

        result = _check_dirty_specs(spec_dir)
        assert result == []

    def test_returns_dirty_spec_files(self, tmp_path):
        from playwright_god.cli import _check_dirty_specs

        spec_dir = tmp_path / "specs"
        spec_dir.mkdir()

        with patch("subprocess.run") as mock_run:
            # Git status: first char is staged status, second is unstaged, then space
            # "M " = unstaged modification (M in first position, space in second)
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="M  specs/login.spec.ts\n",
            )

            result = _check_dirty_specs(spec_dir)

        # M (unstaged) should be detected
        assert "specs/login.spec.ts" in result

    def test_ignores_non_spec_files(self, tmp_path):
        from playwright_god.cli import _check_dirty_specs

        spec_dir = tmp_path / "specs"
        spec_dir.mkdir()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="M utils.ts\n",  # Not a .spec.ts file
            )

            result = _check_dirty_specs(spec_dir)

        assert result == []


class TestPrintPlanDetails:
    """Tests for _print_plan_details helper."""

    def test_prints_add_entries(self, capsys):
        from playwright_god.cli import _print_plan_details
        from playwright_god.update_planner import Bucket, PlanEntry, UpdatePlan

        plan = UpdatePlan(
            add=[
                PlanEntry(bucket=Bucket.ADD, node_id="page:/login", reason="no spec"),
                PlanEntry(bucket=Bucket.ADD, node_id="page:/signup", reason="no spec"),
            ]
        )

        _print_plan_details(plan)
        captured = capsys.readouterr()

        assert "Add" in captured.out
        assert "page:/login" in captured.out
        assert "page:/signup" in captured.out

    def test_prints_update_entries(self, capsys):
        from playwright_god.cli import _print_plan_details
        from playwright_god.update_planner import Bucket, PlanEntry, UpdatePlan

        plan = UpdatePlan(
            update=[
                PlanEntry(
                    bucket=Bucket.UPDATE,
                    spec_path="tests/home.spec.ts",
                    reason="prior run failed",
                ),
            ]
        )

        _print_plan_details(plan)
        captured = capsys.readouterr()

        assert "Update" in captured.out
        assert "home.spec.ts" in captured.out
        assert "failed" in captured.out

    def test_prints_review_entries(self, capsys):
        from playwright_god.cli import _print_plan_details
        from playwright_god.update_planner import Bucket, PlanEntry, UpdatePlan

        plan = UpdatePlan(
            review=[
                PlanEntry(
                    bucket=Bucket.REVIEW,
                    spec_path="tests/orphan.spec.ts",
                    reason="no matching graph node",
                ),
            ]
        )

        _print_plan_details(plan)
        captured = capsys.readouterr()

        assert "Review" in captured.out
        assert "orphan.spec.ts" in captured.out

    def test_truncates_long_lists(self, capsys):
        from playwright_god.cli import _print_plan_details
        from playwright_god.update_planner import Bucket, PlanEntry, UpdatePlan

        plan = UpdatePlan(
            add=[
                PlanEntry(bucket=Bucket.ADD, node_id=f"page:/p{i}", reason="no spec")
                for i in range(25)
            ]
        )

        _print_plan_details(plan)
        captured = capsys.readouterr()

        assert "more" in captured.out  # "... and X more"

    def test_truncates_long_update_list(self, capsys):
        from playwright_god.cli import _print_plan_details
        from playwright_god.update_planner import Bucket, PlanEntry, UpdatePlan

        plan = UpdatePlan(
            update=[
                PlanEntry(bucket=Bucket.UPDATE, spec_path=f"tests/s{i}.spec.ts", reason="failed")
                for i in range(25)
            ]
        )

        _print_plan_details(plan)
        captured = capsys.readouterr()

        assert "Update" in captured.out
        assert "... and 5 more" in captured.out

    def test_truncates_long_review_list(self, capsys):
        from playwright_god.cli import _print_plan_details
        from playwright_god.update_planner import Bucket, PlanEntry, UpdatePlan

        plan = UpdatePlan(
            review=[
                PlanEntry(bucket=Bucket.REVIEW, spec_path=f"tests/r{i}.spec.ts", reason="orphan")
                for i in range(25)
            ]
        )

        _print_plan_details(plan)
        captured = capsys.readouterr()

        assert "Review" in captured.out
        assert "... and 5 more" in captured.out
