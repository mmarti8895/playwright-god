from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from playwright_god.cli import cli
from playwright_god.runner import RunResult, TestCaseResult


def test_inspect_run_reports_launch_plan(tmp_path: Path):
    (tmp_path / "package.json").write_text('{"scripts":{"dev":"vite"}}', encoding="utf-8")
    runner = CliRunner()
    with patch("playwright_god.cli.start_runtime_session") as mock_session:
        mock_session.return_value = MagicMock(
            launch_plan=MagicMock(command="npm run dev", readiness_url="http://127.0.0.1:3000/"),
            ready=True,
            failure_reason=None,
            reachable_urls=("http://127.0.0.1:3000/",),
            unreachable_urls=(),
        )
        result = runner.invoke(cli, ["inspect", str(tmp_path), "--run"])
    assert result.exit_code == 0
    assert "Launch plan" in result.output
    assert "Ready: yes" in result.output


def test_generate_run_writes_evaluation_report(tmp_path: Path):
    runner = CliRunner()
    persist = str(tmp_path / "idx")
    report_dir = tmp_path / "artifacts" / "run1"
    report_dir.mkdir(parents=True)
    with (
        patch("playwright_god.cli.DefaultEmbedder"),
        patch("playwright_god.cli.RepositoryIndexer") as MockIdx,
        patch("playwright_god.cli.PlaywrightTestGenerator") as MockGen,
        patch("playwright_god.cli.RepositoryCrawler") as MockCrawler,
        patch("playwright_god.cli.extract_flow_graph") as MockExtract,
        patch("playwright_god.cli.analyze_repository") as MockProfile,
        patch("playwright_god.cli.TestIndex") as MockTestIndex,
        patch("playwright_god.cli.PlaywrightRunner") as MockRunner,
    ):
        empty_graph = type("FlowGraphStub", (), {"nodes": (), "routes": (), "actions": ()})()
        mock_indexer = MagicMock()
        mock_indexer.count.return_value = 0
        MockIdx.return_value = mock_indexer
        MockCrawler.return_value.crawl.return_value = []
        MockExtract.return_value = empty_graph
        MockProfile.return_value = MagicMock(confidence=0.8, archetype="spa", frameworks=("react",))
        MockTestIndex.build.return_value = MagicMock(
            covered_nodes=lambda: {"route:GET:/existing"},
            covered_journeys=lambda: {"visit:/existing"},
            duplicates_for=lambda **kwargs: [],
            __len__=lambda self: 0,
        )
        mock_gen = MagicMock()
        mock_gen.generate.return_value = 'import { test } from "@playwright/test"; test("x", async ({ page }) => { await page.goto("/new"); });'
        MockGen.return_value = mock_gen
        mock_runner = MagicMock()
        mock_runner.run.return_value = RunResult(
            status="passed",
            duration_ms=5,
            tests=(TestCaseResult(title="x", status="passed", duration_ms=5),),
            exit_code=0,
            stdout="",
            stderr="",
            report_dir=report_dir,
            spec_path=tmp_path / "generated.spec.ts",
        )
        MockRunner.return_value = mock_runner

        result = runner.invoke(
            cli,
            [
                "generate",
                "login flow",
                "-d",
                persist,
                "--provider",
                "template",
                "--run",
                "-o",
                str(tmp_path / "generated.spec.ts"),
            ],
        )
    assert result.exit_code == 0
    eval_path = report_dir / "generated_spec_evaluation.json"
    assert eval_path.exists()
    payload = json.loads(eval_path.read_text(encoding="utf-8"))
    assert payload["status"] == "generated_green"


def test_coverage_report_includes_generation_evaluation(tmp_path: Path):
    runner = CliRunner()
    report_path = tmp_path / "coverage_merged.json"
    report_path.write_text(
        json.dumps(
            {
                "source": "merged",
                "generated_at": "t",
                "totals": {"total_files": 1, "total_lines": 4, "covered_lines": 2, "percent": 50.0},
                "files": {"api.py": {"total_lines": 4, "covered_lines": 2, "percent": 50.0, "missing_line_ranges": [[3, 4]]}},
                "routes": {"total": 1, "covered": [], "uncovered": ["route:GET:/login"]},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "generated_spec_evaluation.json").write_text(
        json.dumps({"status": "generated_green", "route_delta": {"newly_covered": ["route:GET:/login"]}}),
        encoding="utf-8",
    )
    result = runner.invoke(cli, ["coverage", "report", str(report_path)])
    assert result.exit_code == 0
    assert "Generated spec evaluation" in result.output
    assert "Newly covered routes" in result.output
