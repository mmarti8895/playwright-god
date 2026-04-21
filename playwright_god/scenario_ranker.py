"""Rank candidate Playwright scenarios by value, novelty, and likely usefulness."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence


@dataclass(frozen=True)
class CandidateScenario:
    """A ranked candidate scenario for planning or generation."""

    scenario_id: str
    title: str
    target_nodes: tuple[str, ...] = ()
    target_journeys: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    score: float = 0.0
    coverage_gain: float = 0.0
    novelty: float = 0.0
    confidence: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "scenario_id": self.scenario_id,
            "title": self.title,
            "target_nodes": list(self.target_nodes),
            "target_journeys": list(self.target_journeys),
            "reasons": list(self.reasons),
            "score": round(self.score, 3),
            "coverage_gain": round(self.coverage_gain, 3),
            "novelty": round(self.novelty, 3),
            "confidence": round(self.confidence, 3),
        }


def rank_candidate_scenarios(
    *,
    flow_graph=None,
    memory_map: dict | None = None,
    coverage_payload: dict | None = None,
    test_index=None,
    repo_profile=None,
    limit: int = 8,
) -> list[CandidateScenario]:
    """Rank uncovered routes, actions, and feature opportunities."""

    scenarios: list[CandidateScenario] = []
    covered_nodes = set(getattr(test_index, "covered_nodes", lambda: set())())
    covered_journeys = set(getattr(test_index, "covered_journeys", lambda: set())())

    uncovered_route_ids: set[str] = set()
    if isinstance(coverage_payload, dict):
        routes = coverage_payload.get("routes") or {}
        if isinstance(routes, dict):
            uncovered_route_ids = set(routes.get("uncovered") or ())

    for route in tuple(getattr(flow_graph, "routes", ()) or ()):
        novelty = 1.0 if route.id not in covered_nodes else 0.0
        uncovered_bonus = 1.0 if route.id in uncovered_route_ids else 0.0
        confidence = float(getattr(repo_profile, "confidence", 0.5))
        score = 0.5 + novelty * 1.2 + uncovered_bonus * 1.4 + confidence * 0.5
        reasons = []
        if uncovered_bonus:
            reasons.append("uncovered route")
        if novelty:
            reasons.append("not covered by existing tests")
        if route.method == "GET":
            reasons.append("high-confidence entry route")
        scenarios.append(
            CandidateScenario(
                scenario_id=f"route:{route.id}",
                title=f"Exercise {route.method} {route.path}",
                target_nodes=(route.id,),
                target_journeys=(f"visit:{route.path}",),
                reasons=tuple(reasons),
                score=score,
                coverage_gain=uncovered_bonus or novelty,
                novelty=novelty,
                confidence=confidence,
            )
        )

    for action in tuple(getattr(flow_graph, "actions", ()) or ())[:16]:
        journey = f"assert:{action.role}"
        novelty = 1.0 if journey not in covered_journeys else 0.0
        score = 0.35 + novelty * 1.0 + float(getattr(repo_profile, "confidence", 0.5)) * 0.4
        reasons = ["user-visible action"]
        if novelty:
            reasons.append("journey not covered")
        scenarios.append(
            CandidateScenario(
                scenario_id=f"action:{action.id}",
                title=f"Trigger {action.role}",
                target_nodes=(action.id,),
                target_journeys=(journey,),
                reasons=tuple(reasons),
                score=score,
                coverage_gain=novelty * 0.8,
                novelty=novelty,
                confidence=float(getattr(repo_profile, "confidence", 0.5)),
            )
        )

    opportunities = (memory_map or {}).get("test_opportunities") or []
    for item in opportunities[:12]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "Candidate scenario"))
        opportunity_id = str(item.get("opportunity_id", title))
        confidence = float(item.get("confidence", 0.5))
        scenarios.append(
            CandidateScenario(
                scenario_id=f"opportunity:{opportunity_id}",
                title=title,
                reasons=("feature-map opportunity",),
                score=0.4 + confidence,
                coverage_gain=confidence * 0.5,
                novelty=0.5,
                confidence=confidence,
            )
        )

    # Deduplicate by scenario id, keeping highest-score entry.
    best: dict[str, CandidateScenario] = {}
    for scenario in scenarios:
        current = best.get(scenario.scenario_id)
        if current is None or scenario.score > current.score:
            best[scenario.scenario_id] = scenario

    ranked = sorted(
        best.values(),
        key=lambda scenario: (-scenario.score, -scenario.coverage_gain, scenario.title),
    )
    return ranked[:max(0, int(limit))]


def format_ranked_scenarios(scenarios: Sequence[CandidateScenario]) -> str:
    """Render ranked scenarios for prompts and CLI summaries."""

    if not scenarios:
        return ""
    lines = ["Ranked worthwhile targets", "-------------------------"]
    for item in scenarios:
        reasons = ", ".join(item.reasons) if item.reasons else "evidence-backed"
        lines.append(
            f"- {item.title} [score={item.score:.2f}, novelty={item.novelty:.2f}, gain={item.coverage_gain:.2f}]"
        )
        lines.append(f"  why: {reasons}")
    return "\n".join(lines)
