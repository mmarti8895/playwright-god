"""Integration test: extract a flow graph against the bundled fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from playwright_god.extractors import extract
from playwright_god.flow_graph import FlowGraph

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.mark.skipif(
    not (FIXTURES / "sample_app").is_dir(), reason="sample_app fixture missing"
)
def test_extract_against_sample_app(tmp_path):
    graph = extract(FIXTURES / "sample_app")
    assert isinstance(graph, FlowGraph)
    # JSON round-trip is byte-identical (deterministic).
    assert FlowGraph.from_json(graph.to_json()).to_json() == graph.to_json()
    # The sample_app fixture contains an HTML form posting to /api/login.
    assert any(n.kind == "route" for n in graph.nodes)


@pytest.mark.skipif(
    not (FIXTURES / "saml_app").is_dir(), reason="saml_app fixture missing"
)
def test_extract_against_saml_app(tmp_path):
    graph = extract(FIXTURES / "saml_app")
    assert isinstance(graph, FlowGraph)
    # Stable IDs across two runs
    again = extract(FIXTURES / "saml_app")
    assert sorted(graph.node_ids()) == sorted(again.node_ids())


def test_full_pipeline_memory_map_then_coverage(tmp_path):
    # Build a tiny app
    src_dir = tmp_path / "app"
    src_dir.mkdir()
    (src_dir / "api.py").write_text(
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n"
        "@app.get('/healthz')\n"
        "def hz():\n"
        "    return 'ok'\n",
        encoding="utf-8",
    )

    graph = extract(src_dir)
    assert any(n.id == "route:GET:/healthz" for n in graph.nodes)

    # Wire into MemoryMap (schema 2.2)
    from playwright_god.memory_map import build_memory_map, with_flow_graph

    mm = with_flow_graph(build_memory_map([]), graph)
    assert mm["schema_version"] == "2.2"
    assert mm["flow_graph"]["nodes"][0]["kind"] == "route"

    # Wire into coverage merge
    from playwright_god.coverage import (
        CoverageReport,
        FileCoverage,
        coverage_to_dict,
        merge,
    )

    backend = CoverageReport(
        source="backend",
        files={
            "api.py": FileCoverage(
                path="api.py",
                total_lines=5,
                covered_lines=5,
                covered_line_set=frozenset({1, 2, 3, 4, 5}),
            )
        },
        generated_at="t",
    )
    merged = merge(None, backend, flow_graph=graph)
    payload = coverage_to_dict(merged)
    assert payload["routes"]["total"] >= 1
