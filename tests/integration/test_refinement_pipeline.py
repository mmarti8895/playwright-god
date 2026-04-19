"""Integration test for the iterative refinement loop.

Gated behind ``requires_node`` because it shells out via ``PlaywrightRunner``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from playwright_god.refinement import RefinementLoop
from playwright_god.runner import PlaywrightRunner


pytestmark = pytest.mark.requires_node


def test_refinement_pipeline_against_sample_app(tmp_path):
    sample_app = Path(__file__).resolve().parent.parent / "fixtures" / "sample_app"
    if not (sample_app / "package.json").exists():
        pytest.skip("sample_app fixture missing")

    class _StubGen:
        """Always emits a trivially-passing spec (no LLM)."""

        def __init__(self) -> None:
            self.calls = 0

        def generate(self, description, **kwargs):  # noqa: ARG002
            self.calls += 1
            return (
                'import { test, expect } from "@playwright/test";\n'
                'test("smoke", async ({ page }) => {\n'
                "  expect(1 + 1).toBe(2);\n"
                "});\n"
            )

    runner = PlaywrightRunner(target_dir=sample_app, artifact_dir=tmp_path / "runs")
    loop = RefinementLoop(
        generator=_StubGen(),
        runner=runner,
        spec_path=tmp_path / "smoke.spec.ts",
        max_attempts=2,
        log_dir=tmp_path / "audit",
    )
    result = loop.run("smoke check")
    assert result.final_outcome == "passed"
    assert result.log_path is not None and result.log_path.exists()
