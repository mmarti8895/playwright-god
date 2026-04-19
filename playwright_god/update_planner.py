"""DiffPlanner: compares FlowGraph against SpecIndex to produce an UpdatePlan.

The planner classifies specs/nodes into four buckets:

- **add**: graph nodes with no covering spec → generate new specs
- **update**: existing specs whose target changed or prior run failed → regenerate
- **keep**: passing specs on unchanged nodes → leave untouched
- **review**: orphaned specs or pinned specs with stale targets → human review

The plan is serializable to `update_plan.json` for audit and CI consumption.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Literal

from .flow_graph import FlowGraph
from .spec_index import SpecIndex

__all__ = [
    "Bucket",
    "PlanEntry",
    "UpdatePlan",
    "DiffPlanner",
]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


class Bucket(str, Enum):
    """Classification bucket for an update plan entry."""

    ADD = "add"
    UPDATE = "update"
    KEEP = "keep"
    REVIEW = "review"


@dataclass(frozen=True, slots=True)
class PlanEntry:
    """A single entry in the UpdatePlan."""

    bucket: Bucket
    """Which bucket this entry belongs to."""

    node_id: str | None = None
    """Flow-graph node ID (for add/update entries)."""

    spec_path: str | None = None
    """Path to the spec file (for update/keep/review entries)."""

    reason: str = ""
    """Human-readable reason for the classification."""

    prior_run_outcome: str | None = None
    """Prior run status: "passed", "failed", etc. (when applicable)."""

    def to_dict(self) -> dict:
        d: dict = {"bucket": self.bucket.value, "reason": self.reason}
        if self.node_id is not None:
            d["node_id"] = self.node_id
        if self.spec_path is not None:
            d["spec_path"] = self.spec_path
        if self.prior_run_outcome is not None:
            d["prior_run_outcome"] = self.prior_run_outcome
        return d

    @classmethod
    def from_dict(cls, data: dict) -> PlanEntry:
        return cls(
            bucket=Bucket(data["bucket"]),
            node_id=data.get("node_id"),
            spec_path=data.get("spec_path"),
            reason=data.get("reason", ""),
            prior_run_outcome=data.get("prior_run_outcome"),
        )


@dataclass
class UpdatePlan:
    """Typed plan produced by DiffPlanner."""

    add: list[PlanEntry] = field(default_factory=list)
    """Nodes with no covering spec → generate new."""

    update: list[PlanEntry] = field(default_factory=list)
    """Specs whose target changed or failed → regenerate."""

    keep: list[PlanEntry] = field(default_factory=list)
    """Passing specs on unchanged nodes → no action."""

    review: list[PlanEntry] = field(default_factory=list)
    """Orphaned/pinned specs needing human review."""

    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def is_empty(self) -> bool:
        """True if add and update lists are both empty."""
        return len(self.add) == 0 and len(self.update) == 0

    def summary(self) -> dict[str, int]:
        return {
            "add": len(self.add),
            "update": len(self.update),
            "keep": len(self.keep),
            "review": len(self.review),
        }

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "summary": self.summary(),
            "add": [e.to_dict() for e in self.add],
            "update": [e.to_dict() for e in self.update],
            "keep": [e.to_dict() for e in self.keep],
            "review": [e.to_dict() for e in self.review],
        }

    @classmethod
    def from_dict(cls, data: dict) -> UpdatePlan:
        return cls(
            add=[PlanEntry.from_dict(e) for e in data.get("add", [])],
            update=[PlanEntry.from_dict(e) for e in data.get("update", [])],
            keep=[PlanEntry.from_dict(e) for e in data.get("keep", [])],
            review=[PlanEntry.from_dict(e) for e in data.get("review", [])],
            generated_at=data.get("generated_at", ""),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=False)

    @classmethod
    def from_json(cls, text: str) -> UpdatePlan:
        return cls.from_dict(json.loads(text))

    def save(self, path: Path) -> None:
        """Save the plan to a JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> UpdatePlan:
        """Load a plan from a JSON file."""
        return cls.from_json(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# DiffPlanner
# ---------------------------------------------------------------------------


@dataclass
class DiffPlanner:
    """Compares FlowGraph against SpecIndex to produce an UpdatePlan."""

    flow_graph: FlowGraph
    """The current flow graph."""

    spec_index: SpecIndex
    """Index of existing specs."""

    prior_outcomes: dict[str, str] = field(default_factory=dict)
    """Mapping from spec path to prior run outcome ("passed", "failed", etc.)."""

    prior_node_ids: set[str] = field(default_factory=set)
    """Node IDs from the previous flow graph (for detecting renames)."""

    def plan(self) -> UpdatePlan:
        """Build the UpdatePlan by comparing graph and specs."""
        plan = UpdatePlan()

        # Track which nodes are covered
        covered_nodes: set[str] = set()
        processed_specs: set[str] = set()

        # Current graph node IDs
        current_node_ids = {n.id for n in self.flow_graph.nodes}

        # Process each spec in the index
        for entry in self.spec_index:
            processed_specs.add(entry.path)
            spec_node_ids = set(entry.node_ids)

            # Handle pinned specs
            if entry.pinned:
                # Check if pinned spec's target is still in graph
                missing_targets = spec_node_ids - current_node_ids
                if missing_targets:
                    plan.review.append(
                        PlanEntry(
                            bucket=Bucket.REVIEW,
                            spec_path=entry.path,
                            node_id=list(missing_targets)[0] if missing_targets else None,
                            reason="pinned, target missing",
                        )
                    )
                else:
                    # Pinned and targets exist → keep
                    plan.keep.append(
                        PlanEntry(
                            bucket=Bucket.KEEP,
                            spec_path=entry.path,
                            reason="pinned",
                        )
                    )
                covered_nodes.update(spec_node_ids & current_node_ids)
                continue

            # Handle orphan specs (no matching nodes)
            if not spec_node_ids:
                plan.review.append(
                    PlanEntry(
                        bucket=Bucket.REVIEW,
                        spec_path=entry.path,
                        reason="no matching graph node",
                    )
                )
                continue

            # Check node validity
            valid_nodes = spec_node_ids & current_node_ids
            missing_nodes = spec_node_ids - current_node_ids

            if not valid_nodes:
                # All target nodes are gone
                if missing_nodes and self._has_renamed_node(missing_nodes, current_node_ids):
                    # Target was likely renamed
                    new_node = self._find_renamed_target(missing_nodes, current_node_ids)
                    plan.update.append(
                        PlanEntry(
                            bucket=Bucket.UPDATE,
                            spec_path=entry.path,
                            node_id=new_node,
                            reason="target node renamed",
                        )
                    )
                else:
                    plan.review.append(
                        PlanEntry(
                            bucket=Bucket.REVIEW,
                            spec_path=entry.path,
                            node_id=list(missing_nodes)[0] if missing_nodes else None,
                            reason="target node removed",
                        )
                    )
                continue

            # Check prior run outcome
            prior_outcome = self.prior_outcomes.get(entry.path)
            if prior_outcome == "failed":
                plan.update.append(
                    PlanEntry(
                        bucket=Bucket.UPDATE,
                        spec_path=entry.path,
                        node_id=list(valid_nodes)[0],
                        reason="prior run failed",
                        prior_run_outcome="failed",
                    )
                )
                covered_nodes.update(valid_nodes)
                continue

            # Passing spec on valid node → keep
            plan.keep.append(
                PlanEntry(
                    bucket=Bucket.KEEP,
                    spec_path=entry.path,
                    node_id=list(valid_nodes)[0] if valid_nodes else None,
                    reason="passing" if prior_outcome == "passed" else "unchanged",
                    prior_run_outcome=prior_outcome,
                )
            )
            covered_nodes.update(valid_nodes)

        # Find uncovered nodes → add
        for node in self.flow_graph.nodes:
            if node.id not in covered_nodes:
                plan.add.append(
                    PlanEntry(
                        bucket=Bucket.ADD,
                        node_id=node.id,
                        reason="no covering spec",
                    )
                )

        return plan

    def _has_renamed_node(self, missing: set[str], current: set[str]) -> bool:
        """Check if any missing node might have been renamed."""
        # Simple heuristic: same node kind with similar path
        for mid in missing:
            kind = mid.split(":")[0]
            for cid in current:
                if cid.startswith(f"{kind}:"):
                    # Found a node of the same kind - might be a rename
                    return True
        return False

    def _find_renamed_target(self, missing: set[str], current: set[str]) -> str | None:
        """Find the most likely renamed target for missing nodes."""
        # For now, just return the first current node of matching kind
        for mid in missing:
            kind = mid.split(":")[0]
            for cid in current:
                if cid.startswith(f"{kind}:"):
                    return cid
        return None


def load_prior_outcomes(artifact_dir: Path) -> dict[str, str]:
    """Load prior run outcomes from the latest run artifacts.

    Looks for `report.json` in the most recent run directory and extracts
    spec paths and their statuses.
    """
    outcomes: dict[str, str] = {}

    runs_dir = artifact_dir / "runs"
    if not runs_dir.exists():
        return outcomes

    # Find the most recent run directory
    run_dirs = sorted(runs_dir.iterdir(), reverse=True)
    if not run_dirs:
        return outcomes

    latest_run = run_dirs[0]
    report_path = latest_run / "report.json"
    if not report_path.exists():
        return outcomes

    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
        # Handle Playwright JSON report format
        for suite in data.get("suites", []):
            for spec in suite.get("specs", []):
                spec_file = spec.get("file", "")
                # Determine overall status
                tests = spec.get("tests", [])
                if tests:
                    # If any test failed, mark as failed
                    statuses = [t.get("status", "passed") for t in tests]
                    if "failed" in statuses or "timedOut" in statuses:
                        outcomes[spec_file] = "failed"
                    elif "skipped" in statuses:
                        outcomes[spec_file] = "skipped"
                    else:
                        outcomes[spec_file] = "passed"
    except (json.JSONDecodeError, OSError, KeyError):
        pass

    return outcomes
