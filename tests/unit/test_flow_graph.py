"""Unit tests for :mod:`playwright_god.flow_graph`."""

from __future__ import annotations

import json

from playwright_god.flow_graph import (
    EVIDENCE_CAP,
    Action,
    Edge,
    Evidence,
    FlowGraph,
    Route,
    View,
)


# ---------------------------------------------------------------------------
# IDs
# ---------------------------------------------------------------------------


def test_route_id_includes_method_and_path():
    r = Route(method="get", path="/users/{id}")
    assert r.id == "route:GET:/users/{id}"


def test_view_id_includes_file_and_symbol():
    v = View(file="src/pages/Login.tsx")
    assert v.id == "view:src/pages/Login.tsx#default"


def test_action_id_includes_file_line_and_role():
    a = Action(file="src/pages/Login.tsx", line=42, role="submit-login")
    assert a.id == "action:src/pages/Login.tsx:42#submit-login"


def test_evidence_is_capped():
    items = [Evidence(file="f", line_range=(i, i)) for i in range(10)]
    a = Action(file="x.py", line=1, role="r", evidence=tuple(items))
    assert len(a.evidence) == EVIDENCE_CAP == 3
    # Lowest line numbers retained (deterministic ranking)
    assert [e.line_range[0] for e in a.evidence] == [0, 1, 2]


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


def test_to_dict_and_from_dict_roundtrip():
    g = FlowGraph.from_iterables(
        nodes=[
            Route(method="GET", path="/healthz", handler="hz",
                  evidence=(Evidence("api.py", (1, 1)),)),
            View(file="src/App.tsx", symbol="default",
                 evidence=(Evidence("src/App.tsx", (1, 5)),)),
            Action(file="src/App.tsx", line=10, role="login",
                   evidence=(Evidence("src/App.tsx", (10, 10)),)),
        ],
        edges=[Edge("view:src/App.tsx#default", "route:GET:/healthz", "calls")],
    )
    payload = g.to_dict()
    g2 = FlowGraph.from_dict(payload)
    assert g2.to_dict() == payload


def test_json_is_deterministic_across_runs():
    nodes = [
        Route(method="POST", path="/b", evidence=(Evidence("b.py", (1, 1)),)),
        Route(method="GET", path="/a", evidence=(Evidence("a.py", (2, 3)),)),
    ]
    g1 = FlowGraph.from_iterables(nodes)
    g2 = FlowGraph.from_iterables(reversed(nodes))
    assert g1.to_json() == g2.to_json()


def test_from_json_inverse_of_to_json():
    g = FlowGraph.from_iterables(nodes=[Route(method="GET", path="/x")])
    assert FlowGraph.from_json(g.to_json()).to_json() == g.to_json()


def test_unknown_node_kind_raises():
    import pytest
    with pytest.raises(ValueError):
        FlowGraph.from_dict({"nodes": [{"kind": "garbage"}]})


def test_get_returns_node_or_none():
    r = Route(method="GET", path="/x")
    g = FlowGraph.from_iterables([r])
    assert g.get(r.id) is r
    assert g.get("missing") is None


def test_evidence_merged_when_same_node_id_added_twice():
    nodes = [
        Route(method="GET", path="/x", evidence=(Evidence("a.py", (1, 1)),)),
        Route(method="GET", path="/x", evidence=(Evidence("b.py", (2, 2)),)),
    ]
    g = FlowGraph.from_iterables(nodes)
    assert len(g.routes) == 1
    assert {e.file for e in g.routes[0].evidence} == {"a.py", "b.py"}


def test_duplicate_edges_deduplicated():
    """Duplicate edges are removed by from_iterables (line 286 continue)."""
    r = Route(method="GET", path="/x")
    v = View(file="src/App.tsx")
    e1 = Edge(v.id, r.id, "calls")
    e2 = Edge(v.id, r.id, "calls")  # exact duplicate
    g = FlowGraph.from_iterables(nodes=[r, v], edges=[e1, e2])
    assert len(g.edges) == 1
