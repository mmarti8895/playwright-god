"""Unit tests for ``playwright_god.runner``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from playwright_god import runner as runner_mod
from playwright_god.runner import (
    PlaywrightRunner,
    RunnerSetupError,
    RunResult,
    TestCaseResult,
    _filter_env,
    _find_package_json,
    _package_json_has_playwright,
    _parse_report,
)


FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "playwright_report_sample.json"


def _make_pkg(tmp_path: Path, *, with_playwright: bool = True) -> Path:
    pkg: dict[str, Any] = {"name": "demo", "version": "0.0.0"}
    if with_playwright:
        pkg["devDependencies"] = {"@playwright/test": "^1.45.0"}
    (tmp_path / "package.json").write_text(json.dumps(pkg), encoding="utf-8")
    return tmp_path


def _make_spec(target_dir: Path) -> Path:
    spec = target_dir / "tests" / "demo.spec.ts"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text("import { test } from '@playwright/test';\ntest('x', () => {});\n")
    return spec


class _FakeCompleted:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# Pure helpers ---------------------------------------------------------------
def test_filter_env_forwards_credentials_and_playwright_vars() -> None:
    parent = {
        "PATH": "/usr/bin",
        "TEST_USERNAME": "alice",
        "TEST_PASSWORD": "s3cret",
        "PLAYWRIGHT_BROWSERS_PATH": "/cache/pw",
        "UNRELATED": "keep-me",
    }
    out = _filter_env(parent)
    assert out["TEST_USERNAME"] == "alice"
    assert out["TEST_PASSWORD"] == "s3cret"
    assert out["PLAYWRIGHT_BROWSERS_PATH"] == "/cache/pw"
    assert out["PATH"] == "/usr/bin"


def test_filter_env_returns_copy() -> None:
    parent = {"X": "1"}
    out = _filter_env(parent)
    out["X"] = "2"
    assert parent["X"] == "1"


def test_find_package_json_walks_up(tmp_path: Path) -> None:
    root = _make_pkg(tmp_path)
    nested = root / "a" / "b" / "c"
    nested.mkdir(parents=True)
    assert _find_package_json(nested / "spec.ts") == root


def test_package_json_has_playwright_true(tmp_path: Path) -> None:
    _make_pkg(tmp_path, with_playwright=True)
    assert _package_json_has_playwright(tmp_path) is True


def test_package_json_has_playwright_false(tmp_path: Path) -> None:
    _make_pkg(tmp_path, with_playwright=False)
    assert _package_json_has_playwright(tmp_path) is False


def test_package_json_has_playwright_invalid_json(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{not json")
    assert _package_json_has_playwright(tmp_path) is False


def test_parse_report_sample_fixture() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    tests, total_ms = _parse_report(payload)
    statuses = [t.status for t in tests]
    assert "passed" in statuses
    assert "failed" in statuses
    assert "skipped" in statuses
    assert total_ms == 1234 + 567 + 0
    failed = next(t for t in tests if t.status == "failed")
    assert failed.error_message and "Expected" in failed.error_message
    assert failed.trace_path == "/tmp/sample/trace.zip"


def test_parse_report_empty_payload() -> None:
    assert _parse_report({}) == ((), 0)


# check_environment branches -------------------------------------------------
def test_check_env_raises_when_npx_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(runner_mod, "_which", lambda cmd: None)
    with pytest.raises(RunnerSetupError, match="npx not found"):
        PlaywrightRunner().check_environment(tmp_path)


def test_check_env_raises_when_package_json_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(runner_mod, "_which", lambda cmd: "/usr/bin/npx")
    with pytest.raises(RunnerSetupError, match="package.json not found"):
        PlaywrightRunner().check_environment(tmp_path)


def test_check_env_raises_when_playwright_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(runner_mod, "_which", lambda cmd: "/usr/bin/npx")
    _make_pkg(tmp_path, with_playwright=False)
    with pytest.raises(RunnerSetupError, match="@playwright/test"):
        PlaywrightRunner().check_environment(tmp_path)


def test_check_env_passes_when_all_present(tmp_path, monkeypatch):
    monkeypatch.setattr(runner_mod, "_which", lambda cmd: "/usr/bin/npx")
    _make_pkg(tmp_path, with_playwright=True)
    PlaywrightRunner().check_environment(tmp_path)


# run() with mocked subprocess -----------------------------------------------
def _setup_run(tmp_path, monkeypatch, report_payload, returncode, stdout="", stderr=""):
    monkeypatch.setattr(runner_mod, "_which", lambda cmd: "/usr/bin/npx")
    target = _make_pkg(tmp_path, with_playwright=True)
    spec = _make_spec(target)
    captured: list[dict] = []

    def fake_run(cmd, **kwargs):
        captured.append({"cmd": cmd, "kwargs": kwargs})
        env = kwargs.get("env") or {}
        report_path = env.get("PLAYWRIGHT_JSON_OUTPUT_NAME")
        if report_payload is not None and report_path:
            Path(report_path).parent.mkdir(parents=True, exist_ok=True)
            Path(report_path).write_text(json.dumps(report_payload), encoding="utf-8")
        return _FakeCompleted(returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(runner_mod.subprocess, "run", fake_run)
    return spec, captured


def test_run_passed(tmp_path, monkeypatch):
    payload = {
        "suites": [
            {"specs": [{"title": "ok",
                        "tests": [{"results": [{"status": "passed", "duration": 10}]}]}]}
        ]
    }
    spec, captured = _setup_run(tmp_path, monkeypatch, payload, returncode=0)
    result = PlaywrightRunner(target_dir=tmp_path).run(spec)
    assert isinstance(result, RunResult)
    assert result.status == "passed"
    assert result.exit_code == 0
    assert len(result.tests) == 1
    assert result.tests[0].status == "passed"
    assert captured[0]["cmd"][:3] == ["npx", "playwright", "test"]
    assert "--reporter=json" in captured[0]["cmd"]
    assert captured[0]["kwargs"]["check"] is False
    assert captured[0]["kwargs"].get("shell") in (None, False)


def test_run_failed(tmp_path, monkeypatch):
    payload = {
        "suites": [
            {"specs": [{"title": "bad",
                        "tests": [{"results": [{
                            "status": "failed",
                            "duration": 5,
                            "error": {"message": "boom"},
                        }]}]}]}
        ]
    }
    spec, _ = _setup_run(tmp_path, monkeypatch, payload, returncode=1)
    result = PlaywrightRunner(target_dir=tmp_path).run(spec)
    assert result.status == "failed"
    assert result.exit_code == 1
    assert result.tests[0].error_message == "boom"


def test_run_non_passing_status_is_failed(tmp_path, monkeypatch):
    payload = {
        "suites": [
            {"specs": [{"title": "slow",
                        "tests": [{"results": [{"status": "timedOut", "duration": 42}]}]}]}
        ]
    }
    spec, _ = _setup_run(tmp_path, monkeypatch, payload, returncode=0)
    result = PlaywrightRunner(target_dir=tmp_path).run(spec)
    assert result.status == "failed"


def test_run_error_when_no_report(tmp_path, monkeypatch):
    spec, _ = _setup_run(tmp_path, monkeypatch, None, returncode=2, stderr="config crash")
    result = PlaywrightRunner(target_dir=tmp_path).run(spec)
    assert result.status == "error"
    assert result.exit_code == 2
    assert "config crash" in result.stderr


def test_run_falls_back_to_stdout_payload(tmp_path, monkeypatch):
    payload = {
        "suites": [
            {"specs": [{"title": "ok",
                        "tests": [{"results": [{"status": "passed", "duration": 1}]}]}]}
        ]
    }
    spec, _ = _setup_run(tmp_path, monkeypatch, None, returncode=0,
                         stdout=json.dumps(payload))
    result = PlaywrightRunner(target_dir=tmp_path).run(spec)
    assert result.status == "passed"
    assert len(result.tests) == 1


def test_run_artifact_dir_created_with_timestamp(tmp_path, monkeypatch):
    spec, _ = _setup_run(tmp_path, monkeypatch, {"suites": []}, returncode=0)
    artifact_root = tmp_path / "artifacts"
    result = PlaywrightRunner(target_dir=tmp_path, artifact_dir=artifact_root).run(spec)
    assert result.report_dir is not None
    assert result.report_dir.parent == artifact_root
    assert result.report_dir.exists()


def test_run_target_dir_walks_up(tmp_path, monkeypatch):
    spec, _ = _setup_run(tmp_path, monkeypatch, {"suites": []}, returncode=0)
    result = PlaywrightRunner().run(spec)
    assert result.exit_code == 0


def test_run_raises_when_no_package_json_found(tmp_path, monkeypatch):
    deep = tmp_path / "isolated"
    deep.mkdir()
    spec = deep / "x.spec.ts"
    spec.write_text("// noop")
    monkeypatch.setattr(runner_mod, "_find_package_json", lambda p: None)
    monkeypatch.setattr(runner_mod, "_which", lambda cmd: "/usr/bin/npx")
    with pytest.raises(RunnerSetupError, match="No package.json"):
        PlaywrightRunner().run(spec)


# Secret redaction -----------------------------------------------------------
def test_secrets_never_in_runresult_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(runner_mod, "_which", lambda cmd: "/usr/bin/npx")
    target = _make_pkg(tmp_path, with_playwright=True)
    spec = _make_spec(target)

    SECRET_USER = "alice@example.com"
    SECRET_PASS = "hunter2-very-secret"
    monkeypatch.setenv("TEST_USERNAME", SECRET_USER)
    monkeypatch.setenv("TEST_PASSWORD", SECRET_PASS)

    def fake_run(cmd, **kwargs):
        env = kwargs.get("env") or {}
        assert env.get("TEST_USERNAME") == SECRET_USER
        assert env.get("TEST_PASSWORD") == SECRET_PASS
        report_path = env["PLAYWRIGHT_JSON_OUTPUT_NAME"]
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        Path(report_path).write_text(json.dumps({"suites": []}))
        return _FakeCompleted(0, stdout="ok", stderr="")

    monkeypatch.setattr(runner_mod.subprocess, "run", fake_run)
    result = PlaywrightRunner(target_dir=tmp_path).run(spec)

    structured = "|".join([
        repr(result.tests),
        str(result.report_dir),
        str(result.spec_path),
        str(result.exit_code),
        str(result.duration_ms),
        result.status,
        result.stdout,
        result.stderr,
    ])
    assert SECRET_USER not in structured
    assert SECRET_PASS not in structured


# Dataclass shape ------------------------------------------------------------
def test_runresult_is_frozen():
    r = RunResult(status="passed", duration_ms=0, tests=(), exit_code=0, stdout="", stderr="")
    with pytest.raises(Exception):
        r.status = "failed"  # type: ignore[misc]


def test_testcaseresult_is_frozen():
    t = TestCaseResult(title="x", status="passed", duration_ms=0)
    with pytest.raises(Exception):
        t.title = "y"  # type: ignore[misc]
