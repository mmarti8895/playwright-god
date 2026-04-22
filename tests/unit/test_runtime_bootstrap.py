from __future__ import annotations

from unittest.mock import MagicMock

from playwright_god.repo_profile import RepoProfile, StartupCandidate, StateRecipe
from playwright_god.runtime_bootstrap import resolve_launch_plan, start_runtime_session


def _profile() -> RepoProfile:
    return RepoProfile(
        source_root="/repo",
        languages={"typescript": 1},
        frameworks=("react",),
        startup_candidates=(
            StartupCandidate(
                command="npm run dev",
                source="package.json:dev",
                base_url="http://127.0.0.1:3000",
                confidence=0.9,
            ),
        ),
        runtime_targets=(),
        environment_profile={"env_vars": ["TEST_USERNAME", "TEST_PASSWORD"]},
        state_recipes=(
            StateRecipe(
                title="Authenticate before protected flows",
                steps=("Load credentials.", "Persist auth state."),
                kind="auth-bootstrap",
                required_env=("TEST_USERNAME", "TEST_PASSWORD"),
                blocking=True,
            ),
        ),
    )


def test_resolve_launch_plan_collects_env(monkeypatch):
    monkeypatch.setenv("TEST_USERNAME", "alice")
    monkeypatch.setenv("TEST_PASSWORD", "secret")
    plan = resolve_launch_plan(".", _profile())
    assert plan is not None
    assert plan.env["TEST_USERNAME"] == "alice"
    assert plan.readiness_url == "http://127.0.0.1:3000/"
    assert plan.missing_env == ()


def test_start_runtime_session_reports_missing_env(monkeypatch):
    monkeypatch.delenv("TEST_USERNAME", raising=False)
    monkeypatch.delenv("TEST_PASSWORD", raising=False)
    session = start_runtime_session(".", _profile())
    assert session.ready is False
    assert session.failure_reason == "missing required env vars"
    assert session.launch_plan is not None
    assert "TEST_USERNAME" in session.launch_plan.missing_env


def test_start_runtime_session_marks_ready(monkeypatch):
    monkeypatch.setenv("TEST_USERNAME", "alice")
    monkeypatch.setenv("TEST_PASSWORD", "secret")

    class _Proc:
        returncode = None

        stderr = None

        def poll(self):
            return None

        def terminate(self):
            return None

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr("playwright_god.runtime_bootstrap.subprocess.Popen", lambda *a, **k: _Proc())
    monkeypatch.setattr("playwright_god.runtime_bootstrap._url_ok", lambda url: True)
    session = start_runtime_session(".", _profile(), timeout_seconds=0.1)
    assert session.ready is True
    assert session.failure_reason is None
