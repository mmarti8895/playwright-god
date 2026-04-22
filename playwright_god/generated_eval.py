"""Evaluation helpers for generated Playwright specs."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from .runner import RunResult
from .test_index import infer_test_journeys


@dataclass(frozen=True)
class GeneratedSpecEvaluation:
    """Outcome of validating a generated spec for value and executability."""

    status: str
    failure_reason: str | None = None
    newly_covered_nodes: tuple[str, ...] = ()
    newly_covered_journeys: tuple[str, ...] = ()
    duplicate_of: tuple[str, ...] = ()
    route_delta: dict[str, list[str]] | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "failure_reason": self.failure_reason,
            "newly_covered_nodes": list(self.newly_covered_nodes),
            "newly_covered_journeys": list(self.newly_covered_journeys),
            "duplicate_of": list(self.duplicate_of),
            "route_delta": self.route_delta,
        }

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")


def evaluate_generated_spec(
    *,
    spec_content: str,
    generated_nodes: tuple[str, ...] = (),
    test_index=None,
    run_result: RunResult | None = None,
    coverage_before: dict | None = None,
    coverage_after: dict | None = None,
) -> GeneratedSpecEvaluation:
    """Classify a generated spec as valuable, duplicate, or rejected."""

    journeys = infer_test_journeys(spec_content)
    existing_nodes = set(getattr(test_index, "covered_nodes", lambda: set())())
    existing_journeys = set(getattr(test_index, "covered_journeys", lambda: set())())
    newly_nodes = tuple(node for node in generated_nodes if node and node not in existing_nodes)
    newly_journeys = tuple(journey for journey in journeys if journey and journey not in existing_journeys)
    duplicate_of = tuple(
        getattr(test_index, "duplicates_for", lambda **_: [])(
            covered_nodes=generated_nodes,
            covered_journeys=journeys,
        )
        if test_index is not None
        else ()
    )

    route_delta = _route_delta(coverage_before, coverage_after)

    if run_result is None:
        status = "generated_only"
        failure = None
    else:
        outcome = run_result.is_actionable_failure()
        if outcome != "passed":
            status = "generated_rejected"
            failure = outcome
        elif duplicate_of and not newly_nodes and not newly_journeys and not route_delta["newly_covered"]:
            status = "generated_rejected"
            failure = "duplicate coverage"
        elif not newly_nodes and not newly_journeys and not route_delta["newly_covered"]:
            status = "generated_rejected"
            failure = "no measurable coverage gain"
        else:
            status = "generated_green"
            failure = None

    return GeneratedSpecEvaluation(
        status=status,
        failure_reason=failure,
        newly_covered_nodes=newly_nodes,
        newly_covered_journeys=newly_journeys,
        duplicate_of=duplicate_of,
        route_delta=route_delta,
    )


def _route_delta(before: dict | None, after: dict | None) -> dict[str, list[str]]:
    before_cov = _covered_routes(before)
    after_cov = _covered_routes(after)
    return {
        "newly_covered": sorted(after_cov - before_cov),
        "still_uncovered": sorted(_uncovered_routes(after)),
    }


def _covered_routes(payload: dict | None) -> set[str]:
    if not isinstance(payload, dict):
        return set()
    routes = payload.get("routes") or {}
    if isinstance(routes, dict):
        return set(routes.get("covered") or ())
    return set()


def _uncovered_routes(payload: dict | None) -> set[str]:
    if not isinstance(payload, dict):
        return set()
    routes = payload.get("routes") or {}
    if isinstance(routes, dict):
        return set(routes.get("uncovered") or ())
    return set()
