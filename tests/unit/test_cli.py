"""Unit tests for playwright_god.cli."""

from __future__ import annotations

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
            import os
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

            import os
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

            import os
            os.environ.pop("OPENAI_API_KEY", None)

            # mix_stderr=True (default) so stderr is merged into result.output
            result = runner.invoke(
                cli,
                ["generate", "some description", "-d", persist],
            )

        assert result.exit_code == 0
        # The warning is written to stderr (merged into output here)
        assert "Warning" in result.output or "empty" in result.output.lower()
