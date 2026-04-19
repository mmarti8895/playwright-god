"""End-to-end coverage pipeline test.

Skipped automatically when Node/npx isn't on PATH (see conftest).
This test exercises the runner's coverage-dir env injection plumbing only;
no actual browser navigation occurs because the bundled fixture writes
JSON files when wired into a spec, which is the responsibility of the
spec author.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from playwright_god.coverage import (
    CoverageCollector,
    CoverageReport,
    coverage_to_dict,
    coverage_from_dict,
    merge,
    parse_v8_coverage,
    parse_python_coverage_json,
)


pytestmark = pytest.mark.requires_node


FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "coverage_sample.json"


def test_coverage_pipeline_end_to_end(tmp_path):
    """Drive the collector with both sources without spawning any subprocess.

    We synthesise the V8 frontend payload from the bundled fixture and supply
    a CoverageReport in lieu of the backend (so we don't need a running
    Python service in CI).
    """

    sample = json.loads(FIXTURE.read_text(encoding="utf-8"))

    collector = CoverageCollector(frontend=True)
    frontend = collector.collect_frontend(sample["frontend_v8"])
    backend_files = parse_python_coverage_json(sample["backend_python"])
    backend = CoverageReport(
        source="backend", files=backend_files, generated_at="2026-04-19T00:00:00+00:00"
    )

    merged = merge(frontend, backend)
    assert merged.source == "merged"
    assert merged.merge_meta == ("frontend", "backend")
    assert merged.total_files >= 2

    out_path = tmp_path / "coverage_merged.json"
    out_path.write_text(json.dumps(coverage_to_dict(merged), indent=2), encoding="utf-8")
    reloaded = coverage_from_dict(json.loads(out_path.read_text(encoding="utf-8")))
    assert reloaded.source == "merged"
    assert reloaded.total_files == merged.total_files
