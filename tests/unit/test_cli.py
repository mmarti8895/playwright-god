"""Unit tests for playwright_god.cli."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from playwright_god.cli import cli, main


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
        assert "from playwright.sync_api import Page, expect" in result.output

    def test_generate_writes_output_file(self, runner, tmp_path):
        persist = str(tmp_path / "idx")
        output_file = str(tmp_path / "test.spec.py")

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
        assert "def test_" in content

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
        assert "from playwright.sync_api import Page, expect" in result.output

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
        assert "Memory map loaded" in result.stderr
        assert "from playwright.sync_api import Page, expect" in result.output
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
        assert "Warning" in result.stderr

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
        assert 'os.environ.get("TEST_USERNAME", "")' in called_prompt
        assert "Auth type: saml" in result.stderr

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
        assert "Warning: could not read --auth-config" in result.stderr

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
        assert "Warning: could not read --env-file" in result.stderr


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

