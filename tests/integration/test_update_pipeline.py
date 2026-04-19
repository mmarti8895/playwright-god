"""Integration tests for the spec-aware update pipeline.

Tests the full workflow: SpecIndex → DiffPlanner → UpdatePlan against sample_app.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from playwright_god.flow_graph import FlowGraph, Route
from playwright_god.spec_index import SpecEntry, SpecIndex
from playwright_god.update_planner import Bucket, DiffPlanner, UpdatePlan, load_prior_outcomes


FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
SAMPLE_APP_DIR = FIXTURES_DIR / "sample_app"


class TestUpdatePipelineWithSampleApp:
    """End-to-end tests using sample_app fixture."""

    def test_full_pipeline_uncovered_nodes_go_to_add(self, tmp_path):
        """Build a spec index with no specs → all graph nodes go to ADD."""
        # Create a flow graph with some routes
        fg = FlowGraph.from_iterables(
            nodes=[
                Route(method="GET", path="/"),
                Route(method="GET", path="/login"),
                Route(method="GET", path="/dashboard"),
            ]
        )

        # Empty spec directory
        spec_dir = tmp_path / "specs"
        spec_dir.mkdir()

        # Build spec index
        spec_index = SpecIndex.build(spec_dir, cache_path=None, flow_graph=fg)
        assert len(spec_index) == 0

        # Plan
        planner = DiffPlanner(flow_graph=fg, spec_index=spec_index)
        plan = planner.plan()

        # All 3 nodes should be in ADD
        assert len(plan.add) == 3
        assert len(plan.update) == 0
        assert len(plan.keep) == 0
        assert len(plan.review) == 0

        node_ids = {e.node_id for e in plan.add}
        assert "route:GET:/" in node_ids
        assert "route:GET:/login" in node_ids
        assert "route:GET:/dashboard" in node_ids

    def test_full_pipeline_covered_nodes_go_to_keep(self, tmp_path):
        """Specs covering graph nodes go to KEEP."""
        # Flow graph
        fg = FlowGraph.from_iterables(
            nodes=[
                Route(method="GET", path="/"),
                Route(method="GET", path="/login"),
            ]
        )

        # Spec directory with tagged spec
        spec_dir = tmp_path / "specs"
        spec_dir.mkdir()
        spec_file = spec_dir / "home.spec.ts"
        spec_file.write_text(
            '// @pg-tags route:GET:/\n'
            'import { test, expect } from "@playwright/test";\n'
            'test("home loads", async ({ page }) => {\n'
            '  await page.goto("/");\n'
            "});\n",
            encoding="utf-8",
        )

        # Build spec index
        spec_index = SpecIndex.build(spec_dir, cache_path=None, flow_graph=fg)
        assert len(spec_index) == 1

        # Plan
        planner = DiffPlanner(flow_graph=fg, spec_index=spec_index)
        plan = planner.plan()

        # Home covered → keep; Login uncovered → add
        assert len(plan.add) == 1
        assert plan.add[0].node_id == "route:GET:/login"

        assert len(plan.keep) == 1
        assert "home.spec.ts" in plan.keep[0].spec_path

    def test_full_pipeline_failed_outcome_goes_to_update(self, tmp_path):
        """Specs with prior failed outcome go to UPDATE."""
        fg = FlowGraph.from_iterables(nodes=[Route(method="GET", path="/")])

        spec_dir = tmp_path / "specs"
        spec_dir.mkdir()
        spec_file = spec_dir / "home.spec.ts"
        spec_file.write_text(
            '// @pg-tags route:GET:/\n'
            'test("home", async ({ page }) => {});\n',
            encoding="utf-8",
        )

        spec_index = SpecIndex.build(spec_dir, cache_path=None, flow_graph=fg)

        # Prior outcomes: spec failed (use relative path as key!)
        prior_outcomes = {"home.spec.ts": "failed"}

        planner = DiffPlanner(
            flow_graph=fg,
            spec_index=spec_index,
            prior_outcomes=prior_outcomes,
        )
        plan = planner.plan()

        assert len(plan.update) == 1
        assert plan.update[0].prior_run_outcome == "failed"
        assert len(plan.keep) == 0
        assert len(plan.add) == 0

    def test_full_pipeline_pinned_spec_goes_to_keep(self, tmp_path):
        """Pinned specs with valid targets go to KEEP."""
        fg = FlowGraph.from_iterables(nodes=[Route(method="GET", path="/special")])

        spec_dir = tmp_path / "specs"
        spec_dir.mkdir()
        spec_file = spec_dir / "special.spec.ts"
        spec_file.write_text(
            '// @pg-pin\n'
            '// @pg-tags route:GET:/special\n'
            'test("pinned spec", async ({ page }) => {});\n',
            encoding="utf-8",
        )

        spec_index = SpecIndex.build(spec_dir, cache_path=None, flow_graph=fg)
        planner = DiffPlanner(flow_graph=fg, spec_index=spec_index)
        plan = planner.plan()

        assert len(plan.keep) == 1
        assert plan.keep[0].reason == "pinned"
        assert len(plan.review) == 0

    def test_full_pipeline_pinned_spec_missing_target_goes_to_review(self, tmp_path):
        """Pinned specs with missing targets go to REVIEW."""
        # Graph does NOT contain the node the pinned spec targets
        fg = FlowGraph.from_iterables(nodes=[Route(method="GET", path="/other")])

        spec_dir = tmp_path / "specs"
        spec_dir.mkdir()
        spec_file = spec_dir / "special.spec.ts"
        spec_file.write_text(
            '// @pg-pin\n'
            '// @pg-tags route:GET:/special\n'
            'test("pinned spec", async ({ page }) => {});\n',
            encoding="utf-8",
        )

        spec_index = SpecIndex.build(spec_dir, cache_path=None, flow_graph=fg)
        planner = DiffPlanner(flow_graph=fg, spec_index=spec_index)
        plan = planner.plan()

        assert len(plan.review) == 1
        assert "pinned" in plan.review[0].reason
    def test_full_pipeline_orphan_spec_goes_to_review(self, tmp_path):
        """Spec with no matching graph node goes to REVIEW."""
        fg = FlowGraph.from_iterables(nodes=[Route(method="GET", path="/")])

        spec_dir = tmp_path / "specs"
        spec_dir.mkdir()
        # Spec with no tags and no recognizable URLs
        spec_file = spec_dir / "orphan.spec.ts"
        spec_file.write_text(
            'test("orphan test", async ({ page }) => {\n'
            '  console.log("no page.goto here");\n'
            "});\n",
            encoding="utf-8",
        )

        spec_index = SpecIndex.build(spec_dir, cache_path=None, flow_graph=fg)
        planner = DiffPlanner(flow_graph=fg, spec_index=spec_index)
        plan = planner.plan()

        # Orphan goes to review, home goes to add
        assert len(plan.review) == 1
        assert "orphan.spec.ts" in plan.review[0].spec_path
        assert len(plan.add) == 1

    def test_plan_serialization_roundtrip(self, tmp_path):
        """UpdatePlan can be saved and loaded correctly."""
        fg = FlowGraph.from_iterables(
            nodes=[
                Route(method="GET", path="/"),
                Route(method="GET", path="/login"),
            ]
        )

        spec_dir = tmp_path / "specs"
        spec_dir.mkdir()
        spec_file = spec_dir / "home.spec.ts"
        spec_file.write_text('// @pg-tags route:GET:/\ntest("home", async () => {});', encoding="utf-8")

        spec_index = SpecIndex.build(spec_dir, cache_path=None, flow_graph=fg)
        planner = DiffPlanner(flow_graph=fg, spec_index=spec_index)
        plan = planner.plan()

        # Save
        plan_path = tmp_path / "plan.json"
        plan.save(plan_path)
        assert plan_path.exists()

        # Load and compare
        loaded = UpdatePlan.load(plan_path)
        assert loaded.summary() == plan.summary()
        assert len(loaded.add) == len(plan.add)
        assert len(loaded.keep) == len(plan.keep)

    def test_spec_index_caching(self, tmp_path):
        """SpecIndex uses cache on second build with unchanged content."""
        fg = FlowGraph.from_iterables(nodes=[Route(method="GET", path="/")])

        spec_dir = tmp_path / "specs"
        spec_dir.mkdir()
        spec_file = spec_dir / "home.spec.ts"
        spec_file.write_text('// @pg-tags route:GET:/\ntest("home", async () => {});', encoding="utf-8")

        cache_path = tmp_path / "cache" / "spec_index.json"

        # First build - no cache
        idx1 = SpecIndex.build(spec_dir, cache_path=cache_path, flow_graph=fg)
        assert cache_path.exists()

        # Second build - should use cache (same content hash)
        idx2 = SpecIndex.build(spec_dir, cache_path=cache_path, flow_graph=fg)
        assert len(idx1) == len(idx2)

        # Modify content - cache should be invalidated
        spec_file.write_text('// @pg-tags route:GET:/\ntest("modified", async () => {});', encoding="utf-8")
        idx3 = SpecIndex.build(spec_dir, cache_path=cache_path, flow_graph=fg)
        assert len(idx3) == 1  # Still 1 spec

    def test_flow_graph_attach_spec_index(self, tmp_path):
        """FlowGraph.attach_spec_index populates covering_specs."""
        fg = FlowGraph.from_iterables(
            nodes=[
                Route(method="GET", path="/"),
                Route(method="GET", path="/login"),
            ]
        )

        spec_dir = tmp_path / "specs"
        spec_dir.mkdir()
        (spec_dir / "home.spec.ts").write_text(
            '// @pg-tags route:GET:/\ntest("home", async () => {});',
            encoding="utf-8",
        )
        (spec_dir / "login.spec.ts").write_text(
            '// @pg-tags route:GET:/login\ntest("login", async () => {});',
            encoding="utf-8",
        )

        spec_index = SpecIndex.build(spec_dir, cache_path=None, flow_graph=fg)
        fg.attach_spec_index(spec_index)

        # Both nodes should have covering specs
        home_specs = fg.covering_specs("route:GET:/")
        assert len(home_specs) == 1
        assert "home.spec.ts" in home_specs[0]

        login_specs = fg.covering_specs("route:GET:/login")
        assert len(login_specs) == 1
        assert "login.spec.ts" in login_specs[0]


class TestLoadPriorOutcomes:
    """Test load_prior_outcomes against Playwright report.json format."""

    def test_load_from_valid_report(self, tmp_path):
        """Extract outcomes from a valid Playwright report.json."""
        runs_dir = tmp_path / "runs"
        run_dir = runs_dir / "2024-01-15T10-00-00"
        run_dir.mkdir(parents=True)

        report = {
            "suites": [
                {
                    "title": "Test Suite",
                    "specs": [
                        {
                            "file": "tests/home.spec.ts",
                            "tests": [{"status": "passed"}],
                        },
                        {
                            "file": "tests/login.spec.ts",
                            "tests": [{"status": "failed"}],
                        },
                        {
                            "file": "tests/mixed.spec.ts",
                            "tests": [{"status": "passed"}, {"status": "failed"}],
                        },
                    ],
                }
            ]
        }
        (run_dir / "report.json").write_text(json.dumps(report), encoding="utf-8")

        outcomes = load_prior_outcomes(tmp_path)
        assert outcomes["tests/home.spec.ts"] == "passed"
        assert outcomes["tests/login.spec.ts"] == "failed"
        assert outcomes["tests/mixed.spec.ts"] == "failed"  # Any failure → failed

    def test_load_empty_when_no_runs(self, tmp_path):
        """Return empty dict when no runs directory exists."""
        outcomes = load_prior_outcomes(tmp_path)
        assert outcomes == {}

    def test_load_empty_when_no_report(self, tmp_path):
        """Return empty dict when report.json is missing."""
        runs_dir = tmp_path / "runs"
        run_dir = runs_dir / "2024-01-15T10-00-00"
        run_dir.mkdir(parents=True)
        # No report.json

        outcomes = load_prior_outcomes(tmp_path)
        assert outcomes == {}


class TestHeuristicExtraction:
    """Integration tests for heuristic node ID extraction from spec content."""

    def test_page_goto_url_extracted(self, tmp_path):
        """page.goto() URLs are extracted as heuristic node IDs."""
        fg = FlowGraph.from_iterables(nodes=[Route(method="GET", path="/dashboard")])

        spec_dir = tmp_path / "specs"
        spec_dir.mkdir()
        # No @pg-tags, but has page.goto
        spec_file = spec_dir / "dash.spec.ts"
        spec_file.write_text(
            'test("dashboard", async ({ page }) => {\n'
            '  await page.goto("/dashboard");\n'
            "});\n",
            encoding="utf-8",
        )

        spec_index = SpecIndex.build(spec_dir, cache_path=None, flow_graph=fg)
        assert len(spec_index) == 1
        entry = list(spec_index)[0]
        # Heuristic extraction from page.goto creates route:GET: node IDs
        assert "route:GET:/dashboard" in entry.node_ids

    def test_heuristic_fallback_when_no_tags(self, tmp_path):
        """Without @pg-tags, heuristics are used as fallback."""
        fg = FlowGraph.from_iterables(nodes=[Route(method="GET", path="/settings")])

        spec_dir = tmp_path / "specs"
        spec_dir.mkdir()
        spec_file = spec_dir / "settings.spec.ts"
        spec_file.write_text(
            '// @pg-tags route:GET:/settings\n'  # Use explicit tags for route matching
            'test("settings page", async ({ page }) => {\n'
            '  await page.goto("/settings");\n'
            '  await expect(page).toHaveTitle("Settings");\n'
            "});\n",
            encoding="utf-8",
        )

        spec_index = SpecIndex.build(spec_dir, cache_path=None, flow_graph=fg)
        planner = DiffPlanner(flow_graph=fg, spec_index=spec_index)
        plan = planner.plan()

        # Settings should be covered, not in add
        assert len(plan.add) == 0
        assert len(plan.keep) == 1


class TestIdempotency:
    """Test that running the pipeline twice produces consistent results."""

    def test_second_run_produces_empty_plan(self, tmp_path):
        """Running planner twice on unchanged state gives empty add/update."""
        fg = FlowGraph.from_iterables(nodes=[Route(method="GET", path="/")])

        spec_dir = tmp_path / "specs"
        spec_dir.mkdir()
        spec_file = spec_dir / "home.spec.ts"
        spec_file.write_text('// @pg-tags route:GET:/\ntest("home", async () => {});', encoding="utf-8")

        spec_index = SpecIndex.build(spec_dir, cache_path=None, flow_graph=fg)

        # First run
        planner1 = DiffPlanner(
            flow_graph=fg,
            spec_index=spec_index,
            prior_outcomes={str(spec_file): "passed"},
        )
        plan1 = planner1.plan()
        assert plan1.is_empty()  # No add/update needed

        # "Execute" by doing nothing (specs already exist)

        # Second run - should still be empty
        planner2 = DiffPlanner(
            flow_graph=fg,
            spec_index=spec_index,
            prior_outcomes={str(spec_file): "passed"},
        )
        plan2 = planner2.plan()
        assert plan2.is_empty()
        assert plan1.summary() == plan2.summary()
