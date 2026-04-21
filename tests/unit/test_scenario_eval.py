from __future__ import annotations

from playwright_god.flow_graph import Action, Evidence, FlowGraph, Route
from playwright_god.generated_eval import evaluate_generated_spec
from playwright_god.runner import RunResult, TestCaseResult
from playwright_god.scenario_ranker import rank_candidate_scenarios
from playwright_god.test_index import TestIndex, TestIndexEntry


def _graph() -> FlowGraph:
    return FlowGraph.from_iterables(
        nodes=[
            Route(method="GET", path="/login", evidence=(Evidence("a.py", (1, 1)),)),
            Action(file="src/Login.tsx", line=12, role="login-submit"),
        ]
    )


def test_rank_candidate_scenarios_prioritizes_uncovered_routes():
    scenarios = rank_candidate_scenarios(
        flow_graph=_graph(),
        coverage_payload={"routes": {"uncovered": ["route:GET:/login"]}},
        test_index=TestIndex(),
        repo_profile=type("Profile", (), {"confidence": 0.8})(),
    )
    assert scenarios
    assert scenarios[0].title.startswith("Exercise GET /login")


def test_evaluate_generated_spec_rejects_duplicate_without_gain():
    index = TestIndex(
        entries={
            "tests/login.spec.ts": TestIndexEntry(
                path="tests/login.spec.ts",
                owner_framework="playwright",
                covered_nodes=("route:GET:/login",),
                covered_journeys=("visit:/login",),
                assertion_types=("expect",),
                target_urls=("/login",),
                content_hash="abc",
            )
        }
    )
    run = RunResult(
        status="passed",
        duration_ms=5,
        tests=(TestCaseResult(title="login", status="passed", duration_ms=5),),
        exit_code=0,
        stdout="",
        stderr="",
    )
    evaluation = evaluate_generated_spec(
        spec_content='import { test } from "@playwright/test"; test("x", async ({ page }) => { await page.goto("/login"); });',
        generated_nodes=("route:GET:/login",),
        test_index=index,
        run_result=run,
    )
    assert evaluation.status == "generated_rejected"
    assert evaluation.failure_reason == "duplicate coverage"


def test_evaluate_generated_spec_marks_green_with_new_nodes():
    run = RunResult(
        status="passed",
        duration_ms=5,
        tests=(TestCaseResult(title="login", status="passed", duration_ms=5),),
        exit_code=0,
        stdout="",
        stderr="",
    )
    evaluation = evaluate_generated_spec(
        spec_content='import { test } from "@playwright/test"; test("x", async ({ page }) => { await page.goto("/login"); });',
        generated_nodes=("route:GET:/login",),
        test_index=TestIndex(),
        run_result=run,
    )
    assert evaluation.status == "generated_green"
    assert evaluation.newly_covered_nodes == ("route:GET:/login",)
