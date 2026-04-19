"""Flow graph: a deterministic, content-addressed model of an app's surface.

The flow graph augments the chunk-level memory map (schema 2.x) with a
small, well-typed graph of three node kinds — :class:`Route`, :class:`View`,
and :class:`Action` — connected by :class:`Edge` objects.  Every node is
assigned a content-addressed ID (e.g. ``route:GET:/users/{id}``) so that two
extractor runs against the same source produce byte-identical JSON.

Used by:
    * :mod:`playwright_god.extractors` (producers).
    * :mod:`playwright_god.memory_map` (``with_flow_graph``).
    * :mod:`playwright_god.coverage` (``merge(... flow_graph=g)``).
    * :mod:`playwright_god.generator` (``Relevant routes & actions`` block).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from typing import Iterable, Literal, Sequence

EVIDENCE_CAP = 3
"""Maximum number of evidence entries retained per node."""

EdgeKind = Literal["renders", "navigates", "submits", "calls", "handles"]
NodeKind = Literal["route", "view", "action"]


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Evidence:
    """A single (file, line-range) citation backing a node."""

    file: str
    line_range: tuple[int, int]

    def to_dict(self) -> dict:
        return {"file": self.file, "line_range": [int(self.line_range[0]), int(self.line_range[1])]}

    @classmethod
    def from_dict(cls, data: dict) -> "Evidence":
        lr = data.get("line_range") or [0, 0]
        return cls(file=str(data.get("file", "")), line_range=(int(lr[0]), int(lr[1])))


def _cap_evidence(evidence: Sequence[Evidence] | None) -> tuple[Evidence, ...]:
    """Return at most :data:`EVIDENCE_CAP` evidence entries, sorted deterministically.

    Ranking keeps the lowest-line, lexicographically-smallest-file evidence
    first so two runs over the same source agree on the kept set.
    """

    items = list(evidence or ())
    items.sort(key=lambda e: (e.file, e.line_range[0], e.line_range[1]))
    return tuple(items[:EVIDENCE_CAP])


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Route:
    """A server-side endpoint (HTTP method + path + handler symbol)."""

    method: str
    path: str
    handler: str = ""
    evidence: tuple[Evidence, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:  # pragma: no cover — trivial
        object.__setattr__(self, "method", self.method.upper())
        object.__setattr__(self, "evidence", _cap_evidence(self.evidence))

    @property
    def id(self) -> str:
        return f"route:{self.method}:{self.path}"

    @property
    def kind(self) -> NodeKind:
        return "route"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": "route",
            "method": self.method,
            "path": self.path,
            "handler": self.handler,
            "evidence": [e.to_dict() for e in self.evidence],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Route":
        return cls(
            method=str(data.get("method", "GET")),
            path=str(data.get("path", "/")),
            handler=str(data.get("handler", "")),
            evidence=tuple(Evidence.from_dict(e) for e in data.get("evidence") or ()),
        )


@dataclass(frozen=True)
class View:
    """A client-side view/component (file + exported symbol)."""

    file: str
    symbol: str = "default"
    evidence: tuple[Evidence, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:  # pragma: no cover — trivial
        object.__setattr__(self, "evidence", _cap_evidence(self.evidence))

    @property
    def id(self) -> str:
        return f"view:{self.file}#{self.symbol}"

    @property
    def kind(self) -> NodeKind:
        return "view"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": "view",
            "file": self.file,
            "symbol": self.symbol,
            "evidence": [e.to_dict() for e in self.evidence],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "View":
        return cls(
            file=str(data.get("file", "")),
            symbol=str(data.get("symbol", "default")),
            evidence=tuple(Evidence.from_dict(e) for e in data.get("evidence") or ()),
        )


@dataclass(frozen=True)
class Action:
    """A user-actionable element (file + line + role/test-id)."""

    file: str
    line: int
    role: str
    evidence: tuple[Evidence, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:  # pragma: no cover — trivial
        object.__setattr__(self, "evidence", _cap_evidence(self.evidence))

    @property
    def id(self) -> str:
        return f"action:{self.file}:{self.line}#{self.role}"

    @property
    def kind(self) -> NodeKind:
        return "action"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": "action",
            "file": self.file,
            "line": int(self.line),
            "role": self.role,
            "evidence": [e.to_dict() for e in self.evidence],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Action":
        return cls(
            file=str(data.get("file", "")),
            line=int(data.get("line", 0)),
            role=str(data.get("role", "")),
            evidence=tuple(Evidence.from_dict(e) for e in data.get("evidence") or ()),
        )


Node = Route | View | Action


# ---------------------------------------------------------------------------
# Edge
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Edge:
    """A directed connection between two node IDs."""

    source_id: str
    target_id: str
    kind: EdgeKind = "calls"

    def to_dict(self) -> dict:
        return {"source": self.source_id, "target": self.target_id, "kind": self.kind}

    @classmethod
    def from_dict(cls, data: dict) -> "Edge":
        return cls(
            source_id=str(data.get("source", "")),
            target_id=str(data.get("target", "")),
            kind=str(data.get("kind", "calls")),  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------


def _node_from_dict(data: dict) -> Node:
    kind = data.get("kind")
    if kind == "route":
        return Route.from_dict(data)
    if kind == "view":
        return View.from_dict(data)
    if kind == "action":
        return Action.from_dict(data)
    raise ValueError(f"Unknown flow-graph node kind: {kind!r}")


@dataclass(frozen=True)
class FlowGraph:
    """A deterministic collection of routes, views, actions, and edges."""

    nodes: tuple[Node, ...] = field(default_factory=tuple)
    edges: tuple[Edge, ...] = field(default_factory=tuple)

    # Non-frozen mutable state (populated by attach_spec_index)
    _covering_specs: dict[str, list[str]] = field(
        default_factory=dict, repr=False, compare=False, hash=False
    )

    def covering_specs(self, node_id: str) -> list[str]:
        """Return spec paths that cover the given node ID.

        Returns an empty list if no SpecIndex has been attached or no specs
        cover the node.
        """
        return self._covering_specs.get(node_id, [])

    def attach_spec_index(self, spec_index) -> None:
        """Populate covering_specs for all nodes from a SpecIndex.

        Parameters
        ----------
        spec_index
            A :class:`playwright_god.spec_index.SpecIndex` instance with
            entries mapping spec paths to node IDs.
        """
        # Clear existing mappings
        self._covering_specs.clear()

        # Build reverse index: node_id -> [spec_paths]
        for entry in spec_index:
            for node_id in entry.node_ids:
                if node_id not in self._covering_specs:
                    self._covering_specs[node_id] = []
                if entry.path not in self._covering_specs[node_id]:
                    self._covering_specs[node_id].append(entry.path)

        # Sort for determinism
        for node_id in self._covering_specs:
            self._covering_specs[node_id].sort()

    # ---- accessors --------------------------------------------------------
    @property
    def routes(self) -> tuple[Route, ...]:
        return tuple(n for n in self.nodes if isinstance(n, Route))

    @property
    def views(self) -> tuple[View, ...]:
        return tuple(n for n in self.nodes if isinstance(n, View))

    @property
    def actions(self) -> tuple[Action, ...]:
        return tuple(n for n in self.nodes if isinstance(n, Action))

    def node_ids(self) -> tuple[str, ...]:
        return tuple(n.id for n in self.nodes)

    def get(self, node_id: str) -> Node | None:
        for n in self.nodes:
            if n.id == node_id:
                return n
        return None

    # ---- construction -----------------------------------------------------
    @classmethod
    def from_iterables(
        cls,
        nodes: Iterable[Node] = (),
        edges: Iterable[Edge] = (),
    ) -> "FlowGraph":
        """Build a graph with deduplicated, sorted nodes and edges."""

        unique_nodes: dict[str, Node] = {}
        for node in nodes:
            existing = unique_nodes.get(node.id)
            if existing is None:
                unique_nodes[node.id] = node
                continue
            # Merge evidence (cap respected via dataclass post-init)
            merged_ev = tuple(existing.evidence) + tuple(node.evidence)
            unique_nodes[node.id] = replace(existing, evidence=_cap_evidence(merged_ev))

        ordered_nodes = tuple(
            sorted(unique_nodes.values(), key=lambda n: (n.kind, n.id))
        )

        seen_edges: set[tuple[str, str, str]] = set()
        deduped_edges: list[Edge] = []
        for e in edges:
            key = (e.source_id, e.target_id, e.kind)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            deduped_edges.append(e)
        ordered_edges = tuple(
            sorted(deduped_edges, key=lambda e: (e.source_id, e.target_id, e.kind))
        )

        return cls(nodes=ordered_nodes, edges=ordered_edges)

    # ---- serialization ----------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "schema": "flow-graph/1",
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
        }

    def to_json(self) -> str:
        """Return a stable JSON serialization (sorted keys, 2-space indent)."""

        return json.dumps(self.to_dict(), sort_keys=True, indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> "FlowGraph":
        nodes = tuple(_node_from_dict(n) for n in data.get("nodes") or ())
        edges = tuple(Edge.from_dict(e) for e in data.get("edges") or ())
        return cls.from_iterables(nodes, edges)

    @classmethod
    def from_json(cls, payload: str) -> "FlowGraph":
        return cls.from_dict(json.loads(payload))


__all__ = [
    "EVIDENCE_CAP",
    "Action",
    "Edge",
    "Evidence",
    "FlowGraph",
    "Node",
    "Route",
    "View",
]
