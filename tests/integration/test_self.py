"""Self-referential integration tests: playwright-god indexes its own source.

These tests run the full CLI pipeline (``index`` → ``generate``) pointed at
the playwright-god repository itself, verifying that the tool works correctly
when applied to its own codebase.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from click.testing import CliRunner

from playwright_god.cli import cli

# Root of the playwright-god repository (two levels up from this file)
REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def runner():
    return CliRunner()


@pytest.fixture()
def self_index(runner, tmp_path):
    """Index the playwright-god repository itself using the mock embedder."""
    persist = str(tmp_path / "self_idx")
    result = runner.invoke(
        cli,
        [
            "index",
            str(REPO_ROOT),
            "-d", persist,
            "-c", "self",
            "--mock-embedder",
        ],
    )
    assert result.exit_code == 0, f"Index command failed:\n{result.output}"
    assert "Done." in result.output
    return persist


class TestSelfIndex:
    """Verify that playwright-god can index its own source tree."""

    def test_index_exits_cleanly(self, runner, tmp_path):
        persist = str(tmp_path / "idx")
        result = runner.invoke(
            cli,
            ["index", str(REPO_ROOT), "-d", persist, "-c", "self", "--mock-embedder"],
        )
        assert result.exit_code == 0

    def test_index_finds_python_files(self, runner, tmp_path):
        persist = str(tmp_path / "idx")
        result = runner.invoke(
            cli,
            ["index", str(REPO_ROOT), "-d", persist, "-c", "self", "--mock-embedder"],
        )
        assert result.exit_code == 0
        # The crawler should find the Python source files
        assert "Found" in result.output
        # Should report more than zero files
        match = re.search(r"Found (\d+) files", result.output)
        assert match, "Expected 'Found N files' in output"
        assert int(match.group(1)) > 0

    def test_index_reports_chunks_and_vectors(self, runner, tmp_path):
        persist = str(tmp_path / "idx")
        result = runner.invoke(
            cli,
            ["index", str(REPO_ROOT), "-d", persist, "-c", "self", "--mock-embedder"],
        )
        assert result.exit_code == 0
        assert "chunks" in result.output.lower()
        assert "vectors" in result.output.lower() or "index saved" in result.output.lower()

    def test_index_structure_summary_mentions_python(self, runner, tmp_path):
        persist = str(tmp_path / "idx")
        result = runner.invoke(
            cli,
            ["index", str(REPO_ROOT), "-d", persist, "-c", "self", "--mock-embedder"],
        )
        assert result.exit_code == 0
        assert "python" in result.output.lower()


class TestSelfGenerate:
    """Verify that playwright-god generates valid Playwright tests from its own index."""

    def test_generate_rag_pipeline_test(self, runner, self_index):
        """Generate a Playwright test describing the RAG pipeline CLI workflow."""
        result = runner.invoke(
            cli,
            [
                "generate",
                "playwright-god CLI: index a repository and generate a Playwright test",
                "-d", self_index,
                "-c", "self",
                "--mock-embedder",
            ],
        )
        assert result.exit_code == 0
        output = result.output
        assert "@playwright/test" in output
        assert "page.goto" in output

    def test_generate_outputs_typescript(self, runner, self_index):
        """Generated output should be valid TypeScript Playwright test structure."""
        result = runner.invoke(
            cli,
            [
                "generate",
                "index command and generate command of the playwright-god CLI tool",
                "-d", self_index,
                "-c", "self",
                "--mock-embedder",
            ],
        )
        assert result.exit_code == 0
        output = result.output
        # Must contain Playwright test structure
        assert "import" in output
        assert "test(" in output or "test.describe(" in output
        assert "async" in output
        assert "page" in output

    def test_generate_written_to_file(self, runner, self_index, tmp_path):
        """Generated test should be written to the -o output file."""
        out_file = tmp_path / "self.spec.ts"
        result = runner.invoke(
            cli,
            [
                "generate",
                "crawler module that walks a repository directory tree",
                "-d", self_index,
                "-c", "self",
                "--mock-embedder",
                "-o", str(out_file),
            ],
        )
        assert result.exit_code == 0
        assert out_file.exists()
        content = out_file.read_text(encoding="utf-8")
        assert len(content) > 0
        assert "@playwright/test" in content

    def test_generate_with_context_chunks(self, runner, self_index):
        """Requesting more context chunks should still produce valid output."""
        result = runner.invoke(
            cli,
            [
                "generate",
                "embedder and indexer modules used in the RAG pipeline",
                "-d", self_index,
                "-c", "self",
                "--mock-embedder",
                "--n-context", "5",
            ],
        )
        assert result.exit_code == 0
        assert "@playwright/test" in result.output
