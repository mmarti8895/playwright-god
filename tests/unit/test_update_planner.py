"""Unit tests for :mod:`playwright_god.update_planner`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from playwright_god.flow_graph import FlowGraph, Route, View
from playwright_god.spec_index import SpecEntry, SpecIndex
from playwright_god.update_planner import (
    Bucket,
    DiffPlanner,
    PlanEntry,
    UpdatePlan,
    load_prior_outcomes,
)


# ---------------------------------------------------------------------------
# PlanEntry
# ---------------------------------------------------------------------------


def test_plan_entry_to_dict():
    entry = PlanEntry(
        bucket=Bucket.ADD,
        node_id="route:GET:/new",
        reason="no covering spec",
    )
    d = entry.to_dict()
    assert d["bucket"] == "add"
    assert d["node_id"] == "route:GET:/new"
    assert d["reason"] == "no covering spec"
    assert "spec_path" not in d  # None values excluded


def test_plan_entry_roundtrip():
    entry = PlanEntry(
        bucket=Bucket.UPDATE,
        node_id="route:GET:/login",
        spec_path="tests/login.spec.ts",
        reason="prior run failed",
        prior_run_outcome="failed",
    )
    d = entry.to_dict()
    restored = PlanEntry.from_dict(d)
    assert restored == entry


# ---------------------------------------------------------------------------
# UpdatePlan
# ---------------------------------------------------------------------------


def test_update_plan_summary():
    plan = UpdatePlan(
        add=[PlanEntry(Bucket.ADD, node_id="r1", reason="x")],
        update=[PlanEntry(Bucket.UPDATE, spec_path="s1", reason="y")],
        keep=[PlanEntry(Bucket.KEEP, spec_path="s2", reason="z")] * 3,
        review=[],
    )
    summary = plan.summary()
    assert summary == {"add": 1, "update": 1, "keep": 3, "review": 0}


def test_update_plan_is_empty():
    plan = UpdatePlan()
    assert plan.is_empty() is True

    plan_with_add = UpdatePlan(add=[PlanEntry(Bucket.ADD, node_id="r1", reason="x")])
    assert plan_with_add.is_empty() is False


def test_update_plan_json_roundtrip():
    plan = UpdatePlan(
        add=[PlanEntry(Bucket.ADD, node_id="route:GET:/new", reason="no covering spec")],
        update=[PlanEntry(Bucket.UPDATE, spec_path="old.spec.ts", reason="failed")],
    )
    json_str = plan.to_json()
    restored = UpdatePlan.from_json(json_str)
    assert restored.summary() == plan.summary()
    assert restored.add[0].node_id == "route:GET:/new"


def test_update_plan_save_and_load(tmp_path: Path):
    plan = UpdatePlan(
        add=[PlanEntry(Bucket.ADD, node_id="r1", reason="x")],
    )
    plan_path = tmp_path / "update_plan.json"
    plan.save(plan_path)

    loaded = UpdatePlan.load(plan_path)
    assert loaded.summary() == plan.summary()


# ---------------------------------------------------------------------------
# DiffPlanner: ADD bucket
# ---------------------------------------------------------------------------


def test_planner_uncovered_node_goes_to_add():
    """A graph node with no covering spec lands in ADD."""
    fg = FlowGraph.from_iterables([
        Route(method="GET", path="/uncovered"),
    ])
    spec_index = SpecIndex()  # Empty

    planner = DiffPlanner(flow_graph=fg, spec_index=spec_index)
    plan = planner.plan()

    assert len(plan.add) == 1
    assert plan.add[0].node_id == "route:GET:/uncovered"
    assert plan.add[0].reason == "no covering spec"


# ---------------------------------------------------------------------------
# DiffPlanner: UPDATE bucket
# ---------------------------------------------------------------------------


def test_planner_failed_spec_goes_to_update():
    """A spec whose prior run failed lands in UPDATE."""
    fg = FlowGraph.from_iterables([Route(method="GET", path="/login")])
    spec_index = SpecIndex(entries={
        "login.spec.ts": SpecEntry(
            path="login.spec.ts",
            node_ids=("route:GET:/login",),
            content_hash="h1",
        ),
    })

    planner = DiffPlanner(
        flow_graph=fg,
        spec_index=spec_index,
        prior_outcomes={"login.spec.ts": "failed"},
    )
    plan = planner.plan()

    assert len(plan.update) == 1
    assert plan.update[0].spec_path == "login.spec.ts"
    assert plan.update[0].reason == "prior run failed"
    assert plan.update[0].prior_run_outcome == "failed"


def test_planner_renamed_node_goes_to_update():
    """A spec whose target node was renamed lands in UPDATE."""
    # Old graph had /login, new graph has /auth/login
    fg = FlowGraph.from_iterables([Route(method="GET", path="/auth/login")])
    spec_index = SpecIndex(entries={
        "login.spec.ts": SpecEntry(
            path="login.spec.ts",
            node_ids=("route:GET:/login",),  # Old node ID
            content_hash="h1",
        ),
    })

    planner = DiffPlanner(
        flow_graph=fg,
        spec_index=spec_index,
        prior_node_ids={"route:GET:/login"},
    )
    plan = planner.plan()

    assert len(plan.update) == 1
    assert plan.update[0].reason == "target node renamed"


def test_planner_find_renamed_target_returns_matching_kind():
    """_find_renamed_target returns the first current node of matching kind."""
    fg = FlowGraph.from_iterables([Route(method="GET", path="/new")])
    planner = DiffPlanner(flow_graph=fg, spec_index=SpecIndex())

    # Direct test of _find_renamed_target
    missing = {"route:GET:/old"}
    current = {"route:GET:/new"}
    result = planner._find_renamed_target(missing, current)

    assert result == "route:GET:/new"


def test_planner_find_renamed_target_returns_none_when_no_match():
    """_find_renamed_target returns None when no matching kind exists."""
    fg = FlowGraph.from_iterables([])
    planner = DiffPlanner(flow_graph=fg, spec_index=SpecIndex())

    # Route looking for action → no match
    missing = {"route:GET:/old"}
    current = {"view:src/Home.tsx#default"}
    result = planner._find_renamed_target(missing, current)

    assert result is None


# ---------------------------------------------------------------------------
# DiffPlanner: KEEP bucket
# ---------------------------------------------------------------------------


def test_planner_passing_spec_unchanged_node_goes_to_keep():
    """A passing spec on an unchanged node lands in KEEP."""
    fg = FlowGraph.from_iterables([Route(method="GET", path="/dashboard")])
    spec_index = SpecIndex(entries={
        "dashboard.spec.ts": SpecEntry(
            path="dashboard.spec.ts",
            node_ids=("route:GET:/dashboard",),
            content_hash="h1",
        ),
    })

    planner = DiffPlanner(
        flow_graph=fg,
        spec_index=spec_index,
        prior_outcomes={"dashboard.spec.ts": "passed"},
    )
    plan = planner.plan()

    assert len(plan.keep) == 1
    assert plan.keep[0].spec_path == "dashboard.spec.ts"
    assert plan.keep[0].reason == "passing"


def test_planner_spec_without_prior_outcome_goes_to_keep():
    """A spec with no prior outcome (unchanged node) lands in KEEP."""
    fg = FlowGraph.from_iterables([Route(method="GET", path="/profile")])
    spec_index = SpecIndex(entries={
        "profile.spec.ts": SpecEntry(
            path="profile.spec.ts",
            node_ids=("route:GET:/profile",),
            content_hash="h1",
        ),
    })

    planner = DiffPlanner(flow_graph=fg, spec_index=spec_index)
    plan = planner.plan()

    assert len(plan.keep) == 1
    assert plan.keep[0].reason == "unchanged"


# ---------------------------------------------------------------------------
# DiffPlanner: REVIEW bucket
# ---------------------------------------------------------------------------


def test_planner_orphan_spec_goes_to_review():
    """A spec with no matching graph node lands in REVIEW."""
    fg = FlowGraph.from_iterables([])  # Empty graph
    spec_index = SpecIndex(entries={
        "orphan.spec.ts": SpecEntry(
            path="orphan.spec.ts",
            node_ids=(),  # No node IDs
            content_hash="h1",
        ),
    })

    planner = DiffPlanner(flow_graph=fg, spec_index=spec_index)
    plan = planner.plan()

    assert len(plan.review) == 1
    assert plan.review[0].spec_path == "orphan.spec.ts"
    assert plan.review[0].reason == "no matching graph node"


def test_planner_spec_with_removed_node_goes_to_review():
    """A spec whose target node no longer exists lands in REVIEW."""
    fg = FlowGraph.from_iterables([])  # Node removed
    spec_index = SpecIndex(entries={
        "old.spec.ts": SpecEntry(
            path="old.spec.ts",
            node_ids=("route:GET:/removed",),
            content_hash="h1",
        ),
    })

    planner = DiffPlanner(flow_graph=fg, spec_index=spec_index)
    plan = planner.plan()

    assert len(plan.review) == 1
    assert plan.review[0].reason == "target node removed"


# ---------------------------------------------------------------------------
# @pg-pin exclusion
# ---------------------------------------------------------------------------


def test_planner_pinned_spec_stays_in_keep():
    """A @pg-pin spec is never in UPDATE even if its node changed."""
    fg = FlowGraph.from_iterables([Route(method="GET", path="/admin")])
    spec_index = SpecIndex(entries={
        "admin.spec.ts": SpecEntry(
            path="admin.spec.ts",
            node_ids=("route:GET:/admin",),
            content_hash="h1",
            pinned=True,
        ),
    })

    planner = DiffPlanner(
        flow_graph=fg,
        spec_index=spec_index,
        prior_outcomes={"admin.spec.ts": "failed"},  # Would normally trigger UPDATE
    )
    plan = planner.plan()

    assert len(plan.update) == 0
    assert len(plan.keep) == 1
    assert plan.keep[0].spec_path == "admin.spec.ts"
    assert plan.keep[0].reason == "pinned"


def test_planner_pinned_with_missing_target_goes_to_review():
    """A @pg-pin spec whose target is gone lands in REVIEW with special reason."""
    fg = FlowGraph.from_iterables([])  # Target removed
    spec_index = SpecIndex(entries={
        "pinned.spec.ts": SpecEntry(
            path="pinned.spec.ts",
            node_ids=("route:GET:/gone",),
            content_hash="h1",
            pinned=True,
        ),
    })

    planner = DiffPlanner(flow_graph=fg, spec_index=spec_index)
    plan = planner.plan()

    assert len(plan.review) == 1
    assert plan.review[0].spec_path == "pinned.spec.ts"
    assert plan.review[0].reason == "pinned, target missing"


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_planner_idempotent_second_run_empty():
    """Running twice with no changes produces an empty plan."""
    fg = FlowGraph.from_iterables([Route(method="GET", path="/stable")])
    spec_index = SpecIndex(entries={
        "stable.spec.ts": SpecEntry(
            path="stable.spec.ts",
            node_ids=("route:GET:/stable",),
            content_hash="h1",
        ),
    })

    planner = DiffPlanner(
        flow_graph=fg,
        spec_index=spec_index,
        prior_outcomes={"stable.spec.ts": "passed"},
    )
    plan = planner.plan()

    assert plan.is_empty()
    assert len(plan.keep) == 1


# ---------------------------------------------------------------------------
# load_prior_outcomes
# ---------------------------------------------------------------------------


def test_load_prior_outcomes_from_report(tmp_path: Path):
    runs_dir = tmp_path / "runs" / "20260419T120000Z"
    runs_dir.mkdir(parents=True)
    report = {
        "suites": [
            {
                "specs": [
                    {
                        "file": "tests/login.spec.ts",
                        "tests": [{"status": "passed"}],
                    },
                    {
                        "file": "tests/checkout.spec.ts",
                        "tests": [{"status": "failed"}],
                    },
                ]
            }
        ]
    }
    (runs_dir / "report.json").write_text(json.dumps(report))

    outcomes = load_prior_outcomes(tmp_path)
    assert outcomes.get("tests/login.spec.ts") == "passed"
    assert outcomes.get("tests/checkout.spec.ts") == "failed"


def test_load_prior_outcomes_empty_when_no_runs(tmp_path: Path):
    outcomes = load_prior_outcomes(tmp_path)
    assert outcomes == {}


def test_load_prior_outcomes_empty_when_runs_dir_empty(tmp_path: Path):
    """Empty runs directory should return empty outcomes."""
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir(parents=True)
    # runs/ exists but has no subdirectories
    outcomes = load_prior_outcomes(tmp_path)
    assert outcomes == {}


def test_load_prior_outcomes_handles_corrupt_report(tmp_path: Path):
    runs_dir = tmp_path / "runs" / "20260419T120000Z"
    runs_dir.mkdir(parents=True)
    (runs_dir / "report.json").write_text("not valid json")

    outcomes = load_prior_outcomes(tmp_path)
    assert outcomes == {}


def test_load_prior_outcomes_handles_skipped_tests(tmp_path: Path):
    """Skipped tests should be marked as skipped."""
    runs_dir = tmp_path / "runs" / "20260419T120000Z"
    runs_dir.mkdir(parents=True)
    report = {
        "suites": [
            {
                "specs": [
                    {
                        "file": "tests/skipped.spec.ts",
                        "tests": [{"status": "skipped"}],
                    },
                ]
            }
        ]
    }
    (runs_dir / "report.json").write_text(json.dumps(report))

    outcomes = load_prior_outcomes(tmp_path)
    assert outcomes.get("tests/skipped.spec.ts") == "skipped"
