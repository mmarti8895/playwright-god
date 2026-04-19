"""End-to-end integration test for ``PlaywrightRunner``.

Skipped automatically when ``npx`` is not on PATH (see ``tests/conftest.py``).
The test bootstraps a tiny throwaway Playwright project and a single trivial
spec, then asserts that ``PlaywrightRunner.run`` returns a passing
``RunResult``. A real ``@playwright/test`` install is required.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from playwright_god.runner import PlaywrightRunner, RunnerSetupError


pytestmark = pytest.mark.requires_node


def _have_playwright_installed(target: Path) -> bool:
    """Best-effort check that @playwright/test is installed in target/node_modules."""

    return (target / "node_modules" / "@playwright" / "test" / "package.json").is_file()


@pytest.fixture(scope="module")
def playwright_project(tmp_path_factory) -> Path:
    """Create a minimal Playwright project; install @playwright/test if missing."""

    target = tmp_path_factory.mktemp("pw_proj")
    (target / "package.json").write_text(
        json.dumps(
            {
                "name": "runner-it",
                "version": "0.0.0",
                "private": True,
                "devDependencies": {"@playwright/test": "^1.45.0"},
            }
        ),
        encoding="utf-8",
    )
    (target / "playwright.config.ts").write_text(
        "import { defineConfig } from '@playwright/test';\n"
        "export default defineConfig({ testDir: 'tests', reporter: 'json', "
        "use: { headless: true } });\n",
        encoding="utf-8",
    )
    spec_dir = target / "tests"
    spec_dir.mkdir()
    (spec_dir / "smoke.spec.ts").write_text(
        "import { test, expect } from '@playwright/test';\n"
        "test('passes trivially', async () => { expect(1 + 1).toBe(2); });\n",
        encoding="utf-8",
    )

    # Try to install the dep. If npm isn't around, the test will fail-skip below.
    if not _have_playwright_installed(target):
        npm = shutil.which("npm")
        if npm is None:
            pytest.skip("npm not available to install @playwright/test")
        proc = subprocess.run(
            [npm, "install", "--no-audit", "--no-fund", "--silent"],
            cwd=str(target),
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0 or not _have_playwright_installed(target):
            pytest.skip(
                "could not install @playwright/test "
                f"(exit {proc.returncode}): {proc.stderr[:200]}"
            )

    return target


def test_runner_executes_passing_spec(playwright_project: Path) -> None:
    spec = playwright_project / "tests" / "smoke.spec.ts"
    runner = PlaywrightRunner(target_dir=playwright_project)
    result = runner.run(spec)
    assert result.status == "passed", (
        f"expected passed, got {result.status}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert result.exit_code == 0
    assert any(t.status == "passed" for t in result.tests)
    assert result.report_dir is not None and result.report_dir.exists()


def test_runner_setup_error_when_target_dir_lacks_package_json(tmp_path: Path) -> None:
    spec = tmp_path / "x.spec.ts"
    spec.write_text("// noop")
    with pytest.raises(RunnerSetupError):
        PlaywrightRunner(target_dir=tmp_path).run(spec)
