"""Playwright runner: execute generated specs and capture structured results.

This module shells out to ``npx playwright test --reporter=json`` and parses
the resulting JSON reporter payload into typed Python dataclasses. It is the
foundational dependency of the coverage-aware-planning, iterative-refinement,
and spec-aware-update changes.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping, Sequence

# Environment variables forwarded to the Playwright subprocess. These are
# never logged or included in any RunResult field.
_FORWARDED_ENV_PREFIXES: tuple[str, ...] = ("PLAYWRIGHT_",)
_FORWARDED_ENV_NAMES: tuple[str, ...] = ("TEST_USERNAME", "TEST_PASSWORD")

# Status literals used across RunResult / TestCaseResult.
RunStatus = Literal["passed", "failed", "error"]
TestStatus = Literal["passed", "failed", "skipped", "timedOut", "interrupted"]


class RunnerSetupError(RuntimeError):
    """Raised when the host is missing a prerequisite for running Playwright.

    Always carries an actionable remediation message.
    """


@dataclass(frozen=True)
class TestCaseResult:
    """Outcome of a single test case within a run."""

    # Tell pytest not to try to collect this dataclass as a test class.
    __test__ = False

    title: str
    status: TestStatus
    duration_ms: int
    error_message: str | None = None
    trace_path: str | None = None


@dataclass(frozen=True)
class RunResult:
    """Structured result of a Playwright run.

    The shape is deliberately stable so downstream features
    (coverage-aware-planning, iterative-refinement, spec-aware-update) can
    consume it without re-parsing reporter output.
    """

    status: RunStatus
    duration_ms: int
    tests: tuple[TestCaseResult, ...]
    exit_code: int
    stdout: str
    stderr: str
    report_dir: Path | None = None
    spec_path: Path | None = None
    coverage_raw: tuple[dict, ...] = ()


def _which(cmd: str) -> str | None:
    """Thin wrapper around ``shutil.which`` so it can be monkeypatched."""

    return shutil.which(cmd)


def _find_package_json(start: Path) -> Path | None:
    """Walk upward from ``start`` until a ``package.json`` is found."""

    current = start if start.is_dir() else start.parent
    for candidate in (current, *current.parents):
        if (candidate / "package.json").is_file():
            return candidate
    return None


def _package_json_has_playwright(pkg_dir: Path) -> bool:
    """Return True iff ``@playwright/test`` is listed as a (dev) dependency."""

    try:
        with (pkg_dir / "package.json").open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return False

    for section in ("dependencies", "devDependencies", "peerDependencies"):
        deps = data.get(section)
        if isinstance(deps, dict) and "@playwright/test" in deps:
            return True
    return False


def _filter_env(parent_env: Mapping[str, str]) -> dict[str, str]:
    """Produce the subprocess environment.

    Forwards everything from the parent (so PATH etc. work) plus an explicit
    pass-through of TEST_USERNAME, TEST_PASSWORD, and any PLAYWRIGHT_* vars.
    Values are never logged.
    """

    env = dict(parent_env)
    # All listed vars are already in parent_env via dict() above; the explicit
    # listing below is the contract surface for the spec scenarios.
    for name in _FORWARDED_ENV_NAMES:
        if name in parent_env:
            env[name] = parent_env[name]
    for key, value in parent_env.items():
        if any(key.startswith(prefix) for prefix in _FORWARDED_ENV_PREFIXES):
            env[key] = value
    return env


def _timestamp() -> str:
    """Return a filesystem-safe ISO-8601 timestamp (UTC)."""

    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _parse_report(payload: dict) -> tuple[tuple[TestCaseResult, ...], int]:
    """Parse Playwright's JSON reporter payload into per-test results.

    Returns ``(tests, total_duration_ms)``.
    """

    tests: list[TestCaseResult] = []
    total_ms = 0

    def _walk(suite: dict) -> None:
        nonlocal total_ms
        for spec in suite.get("specs", []) or []:
            title = spec.get("title", "<unknown>")
            for spec_test in spec.get("tests", []) or []:
                for result in spec_test.get("results", []) or []:
                    duration = int(result.get("duration", 0) or 0)
                    total_ms += duration
                    status = result.get("status", "failed")
                    error_message = None
                    err = result.get("error") or (result.get("errors") or [None])[0]
                    if isinstance(err, dict):
                        error_message = err.get("message") or err.get("stack")
                    elif isinstance(err, str):
                        error_message = err

                    trace_path: str | None = None
                    for attachment in result.get("attachments", []) or []:
                        if attachment.get("name") == "trace":
                            trace_path = attachment.get("path")
                            break

                    tests.append(
                        TestCaseResult(
                            title=title,
                            status=status,
                            duration_ms=duration,
                            error_message=error_message,
                            trace_path=trace_path,
                        )
                    )
        for child in suite.get("suites", []) or []:
            _walk(child)

    for suite in payload.get("suites", []) or []:
        _walk(suite)

    return tuple(tests), total_ms


class PlaywrightRunner:
    """Adapter around ``npx playwright test --reporter=json``.

    Parameters
    ----------
    target_dir:
        Directory containing the ``package.json`` with ``@playwright/test``.
        If ``None``, resolved by walking up from the spec's parent.
    artifact_dir:
        Root directory under which per-run artifact subdirectories are created.
        Defaults to ``<target_dir>/.pg_runs``.
    reporter:
        Playwright reporter to request. ``"json"`` is required for parsing.
    extra_args:
        Additional CLI arguments forwarded to ``npx playwright test``.
    coverage:
        When True, set ``PLAYWRIGHT_GOD_COVERAGE_DIR`` so the bundled JS
        coverage fixture (see ``playwright_god/_assets/coverage_fixture.ts``)
        writes per-test V8 payloads we can pick up. The runner does not
        inject the fixture import itself; the spec or ``playwright.config.ts``
        is responsible for using the fixture. After the run, all
        ``*.coverage.json`` files under that directory are loaded into
        ``RunResult.coverage_raw``.
    """

    def __init__(
        self,
        *,
        target_dir: Path | str | None = None,
        artifact_dir: Path | str | None = None,
        reporter: str = "json",
        extra_args: Sequence[str] = (),
        coverage: bool = False,
    ) -> None:
        self._target_dir = Path(target_dir).resolve() if target_dir else None
        self._artifact_dir = Path(artifact_dir) if artifact_dir else None
        self._reporter = reporter
        self._extra_args = tuple(extra_args)
        self._coverage = bool(coverage)

    # ------------------------------------------------------------------
    # Environment / prerequisite checks
    # ------------------------------------------------------------------
    def check_environment(self, target_dir: Path) -> None:
        """Validate that npx and ``@playwright/test`` are reachable.

        Raises ``RunnerSetupError`` with an actionable message on any miss.
        """

        if _which("npx") is None:
            raise RunnerSetupError(
                "npx not found on PATH; install Node 18+ from https://nodejs.org "
                "and re-run."
            )
        if not (target_dir / "package.json").is_file():
            raise RunnerSetupError(
                f"package.json not found in {target_dir}; pass --target-dir to "
                "point at the directory that contains your Playwright project."
            )
        if not _package_json_has_playwright(target_dir):
            raise RunnerSetupError(
                "@playwright/test is not listed in package.json dependencies; "
                "install it with `npm i -D @playwright/test`."
            )

    # ------------------------------------------------------------------
    # Working directory resolution
    # ------------------------------------------------------------------
    def _resolve_target_dir(self, spec_path: Path) -> Path:
        if self._target_dir is not None:
            return self._target_dir
        found = _find_package_json(spec_path.resolve())
        if found is None:
            raise RunnerSetupError(
                f"No package.json found in any parent of {spec_path}; pass "
                "--target-dir to specify the Playwright project root."
            )
        return found

    # ------------------------------------------------------------------
    # Artifact directory layout
    # ------------------------------------------------------------------
    def _resolve_artifact_dir(self, target_dir: Path) -> Path:
        root = self._artifact_dir or (target_dir / ".pg_runs")
        run_dir = Path(root) / _timestamp()
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------
    def run(self, spec_path: Path | str) -> RunResult:
        """Execute the Playwright spec(s) at ``spec_path`` and return a RunResult."""

        spec_path = Path(spec_path)
        target_dir = self._resolve_target_dir(spec_path)
        self.check_environment(target_dir)

        run_dir = self._resolve_artifact_dir(target_dir)
        report_path = run_dir / "report.json"

        # Build relative spec arg when the spec is inside the target dir for
        # cleaner output, otherwise pass the absolute path verbatim.
        try:
            spec_arg = str(spec_path.resolve().relative_to(target_dir))
        except ValueError:
            spec_arg = str(spec_path.resolve())

        cmd = [
            "npx",
            "playwright",
            "test",
            spec_arg,
            f"--reporter={self._reporter}",
            *self._extra_args,
        ]

        env = _filter_env(os.environ)
        # Tell Playwright where to write the JSON report file.
        env["PLAYWRIGHT_JSON_OUTPUT_NAME"] = str(report_path)
        # And the HTML/trace artifacts directory.
        env["PLAYWRIGHT_HTML_REPORT"] = str(run_dir / "html")

        # Coverage capture: tell the bundled JS fixture where to drop V8 payloads.
        coverage_dir: Path | None = None
        if self._coverage:
            coverage_dir = run_dir / "coverage"
            coverage_dir.mkdir(parents=True, exist_ok=True)
            env["PLAYWRIGHT_GOD_COVERAGE_DIR"] = str(coverage_dir)

        completed = subprocess.run(
            cmd,
            cwd=str(target_dir),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        # Collect any V8 coverage payloads dropped by the JS fixture.
        coverage_raw_payload: tuple[dict, ...] = ()
        if coverage_dir is not None and coverage_dir.is_dir():
            entries: list[dict] = []
            for cov_file in sorted(coverage_dir.glob("*.coverage.json")):
                try:
                    with cov_file.open("r", encoding="utf-8") as fh:
                        data = json.load(fh)
                except (OSError, json.JSONDecodeError):
                    continue
                if isinstance(data, list):
                    entries.extend(d for d in data if isinstance(d, dict))
                elif isinstance(data, dict):
                    entries.append(data)
            coverage_raw_payload = tuple(entries)

        # Parse reporter output. Prefer the file (more reliable than stdout
        # which can be interleaved with progress lines).
        payload: dict | None = None
        if report_path.is_file():
            try:
                with report_path.open("r", encoding="utf-8") as fh:
                    payload = json.load(fh)
            except (OSError, json.JSONDecodeError):
                payload = None
        if payload is None and completed.stdout.strip().startswith("{"):
            try:
                payload = json.loads(completed.stdout)
            except json.JSONDecodeError:
                payload = None

        if payload is None:
            return RunResult(
                status="error",
                duration_ms=0,
                tests=(),
                exit_code=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
                report_dir=run_dir,
                spec_path=spec_path,
                coverage_raw=coverage_raw_payload,
            )

        tests, duration_ms = _parse_report(payload)
        if completed.returncode == 0 and all(t.status in ("passed", "skipped") for t in tests):
            status: RunStatus = "passed"
        else:
            status = "failed"

        return RunResult(
            status=status,
            duration_ms=duration_ms,
            tests=tests,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            report_dir=run_dir,
            spec_path=spec_path,
            coverage_raw=coverage_raw_payload,
        )


__all__ = [
    "PlaywrightRunner",
    "RunResult",
    "TestCaseResult",
    "RunnerSetupError",
    "RunStatus",
    "TestStatus",
]
