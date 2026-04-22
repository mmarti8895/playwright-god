"""Runtime bootstrap and readiness checks for repository-backed test runs."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import shlex
import subprocess
import time
from typing import Sequence
from urllib import error, parse, request

from .repo_profile import RepoProfile, StartupCandidate


@dataclass(frozen=True)
class LaunchPlan:
    """A deterministic launch choice derived from repository profiling."""

    command: str
    working_dir: str
    env: dict[str, str] = field(default_factory=dict)
    missing_env: tuple[str, ...] = ()
    port: int | None = None
    readiness_url: str | None = None
    timeout_seconds: float = 20.0
    source: str = "inferred"
    confidence: float = 0.5

    def to_dict(self) -> dict[str, object]:
        return {
            "command": self.command,
            "working_dir": self.working_dir,
            "env": dict(self.env),
            "missing_env": list(self.missing_env),
            "port": self.port,
            "readiness_url": self.readiness_url,
            "timeout_seconds": self.timeout_seconds,
            "source": self.source,
            "confidence": round(self.confidence, 3),
        }


@dataclass(frozen=True)
class RuntimeSession:
    """Result of attempting to launch and probe the target application."""

    attempted: bool
    launch_plan: LaunchPlan | None = None
    ready: bool = False
    failure_reason: str | None = None
    reachable_urls: tuple[str, ...] = ()
    unreachable_urls: tuple[str, ...] = ()
    selected_recipe: dict[str, object] | None = None
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "attempted": self.attempted,
            "launch_plan": self.launch_plan.to_dict() if self.launch_plan is not None else None,
            "ready": self.ready,
            "failure_reason": self.failure_reason,
            "reachable_urls": list(self.reachable_urls),
            "unreachable_urls": list(self.unreachable_urls),
            "selected_recipe": self.selected_recipe,
            "notes": list(self.notes),
        }


def resolve_launch_plan(
    root: str | Path,
    profile: RepoProfile,
    *,
    timeout_seconds: float = 20.0,
) -> LaunchPlan | None:
    """Choose the highest-confidence startup candidate and build a launch plan."""

    if not profile.startup_candidates:
        return None
    candidate = profile.startup_candidates[0]
    readiness_url = _resolve_readiness_url(profile, candidate)
    env_vars = tuple(str(item) for item in (profile.environment_profile.get("env_vars") or ()))
    selected_env = {
        name: value
        for name, value in os.environ.items()
        if name in env_vars
    }
    required_env = _required_env_names(profile)
    missing_env = tuple(name for name in required_env if name not in selected_env)
    return LaunchPlan(
        command=candidate.command,
        working_dir=_resolve_working_dir(root, candidate),
        env=selected_env,
        missing_env=missing_env,
        port=_port_from_url(readiness_url),
        readiness_url=readiness_url,
        timeout_seconds=timeout_seconds,
        source=candidate.source,
        confidence=candidate.confidence,
    )


def start_runtime_session(
    root: str | Path,
    profile: RepoProfile,
    *,
    timeout_seconds: float = 20.0,
) -> RuntimeSession:
    """Launch the app and wait for readiness using the chosen launch plan."""

    plan = resolve_launch_plan(root, profile, timeout_seconds=timeout_seconds)
    if plan is None:
        return RuntimeSession(
            attempted=False,
            failure_reason="no startup candidate inferred",
            notes=("No startup candidate was available for runtime bootstrap.",),
        )
    selected_recipe = _select_blocking_recipe(profile)
    if plan.missing_env:
        return RuntimeSession(
            attempted=False,
            launch_plan=plan,
            ready=False,
            failure_reason="missing required env vars",
            selected_recipe=selected_recipe,
            notes=("Missing required env vars: " + ", ".join(plan.missing_env),),
        )

    root_path = Path(root).resolve()
    cwd = root_path / plan.working_dir if plan.working_dir != "." else root_path
    command_parts = shlex.split(plan.command)
    if not command_parts:
        return RuntimeSession(
            attempted=False,
            launch_plan=plan,
            ready=False,
            failure_reason="empty startup command",
            selected_recipe=selected_recipe,
        )

    process: subprocess.Popen[str] | None = None
    try:
        env = dict(os.environ)
        env.update(plan.env)
        process = subprocess.Popen(
            command_parts,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except (OSError, ValueError) as exc:
        return RuntimeSession(
            attempted=True,
            launch_plan=plan,
            ready=False,
            failure_reason=str(exc),
            selected_recipe=selected_recipe,
            notes=(f"Could not start `{plan.command}`: {exc}",),
        )

    try:
        probe_urls = _probe_urls(profile, plan)
        reachable: list[str] = []
        remaining = list(probe_urls)
        deadline = time.time() + plan.timeout_seconds
        while time.time() < deadline and remaining:
            pending: list[str] = []
            for url in remaining:
                if _url_ok(url):
                    reachable.append(url)
                else:
                    pending.append(url)
            if reachable:
                break
            remaining = pending
            time.sleep(0.5)
        failure_reason = None
        notes: list[str] = []
        if not reachable:
            failure_reason = "readiness check timed out"
        if process.poll() is not None and process.returncode not in (0, None):
            stderr = ""
            try:
                assert process.stderr is not None
                stderr = process.stderr.read(500).strip()
            except OSError:
                stderr = ""
            if stderr:
                failure_reason = stderr if failure_reason is None else failure_reason
                notes.append(f"process exited early: {stderr}")
        return RuntimeSession(
            attempted=True,
            launch_plan=plan,
            ready=bool(reachable),
            failure_reason=failure_reason,
            reachable_urls=tuple(reachable),
            unreachable_urls=tuple(url for url in probe_urls if url not in reachable),
            selected_recipe=selected_recipe,
            notes=tuple(notes),
        )
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)


def runtime_context_block(profile: RepoProfile, session: RuntimeSession) -> str:
    """Return a prompt block describing runtime bootstrap state."""

    lines = ["Runtime bootstrap", "-----------------"]
    if session.launch_plan is not None:
        lines.append(f"Launch plan: {session.launch_plan.command}")
        lines.append(f"Readiness URL: {session.launch_plan.readiness_url or 'n/a'}")
    lines.append(f"Ready: {'yes' if session.ready else 'no'}")
    if session.failure_reason:
        lines.append(f"Failure reason: {session.failure_reason}")
    if session.selected_recipe:
        lines.append(
            "Selected setup recipe: "
            f"{session.selected_recipe.get('title', 'unknown')} "
            f"(kind={session.selected_recipe.get('kind', 'generic')})"
        )
    if session.reachable_urls:
        lines.append("Reachable URLs: " + ", ".join(session.reachable_urls[:6]))
    if session.unreachable_urls:
        lines.append("Unreachable URLs: " + ", ".join(session.unreachable_urls[:6]))
    if profile.state_recipes:
        for recipe in profile.state_recipes[:3]:
            lines.append(
                f"Recipe {recipe.kind}: {'; '.join(recipe.steps)}"
            )
    return "\n".join(lines)


def _resolve_working_dir(root: str | Path, candidate: StartupCandidate) -> str:
    root_path = Path(root).resolve()
    candidate_dir = candidate.working_dir or "."
    target = root_path / candidate_dir
    if target.exists():
        return candidate_dir
    return "."


def _resolve_readiness_url(profile: RepoProfile, candidate: StartupCandidate) -> str | None:
    if candidate.base_url:
        return candidate.base_url.rstrip("/") + "/"
    for target in profile.runtime_targets:
        if target.base_url:
            return target.base_url.rstrip("/") + target.path
    return None


def _port_from_url(url: str | None) -> int | None:
    if not url:
        return None
    parsed = parse.urlparse(url)
    if parsed.port is not None:
        return parsed.port
    if parsed.scheme == "https":
        return 443
    if parsed.scheme == "http":
        return 80
    return None


def _required_env_names(profile: RepoProfile) -> tuple[str, ...]:
    env_vars = tuple(str(item) for item in (profile.environment_profile.get("env_vars") or ()))
    auth_required = [
        name for name in env_vars if any(token in name.upper() for token in ("USER", "PASS", "TOKEN", "KEY"))
    ]
    if auth_required:
        return tuple(dict.fromkeys(auth_required))
    return ()


def _probe_urls(profile: RepoProfile, plan: LaunchPlan) -> list[str]:
    urls: list[str] = []
    if plan.readiness_url:
        urls.append(plan.readiness_url)
    for target in profile.runtime_targets[:8]:
        if target.base_url:
            urls.append(target.base_url.rstrip("/") + target.path)
    return list(dict.fromkeys(urls))


def _url_ok(url: str) -> bool:
    try:
        req = request.Request(url, method="GET")
        with request.urlopen(req, timeout=1.5) as response:
            return 200 <= getattr(response, "status", 0) < 500
    except (error.URLError, ValueError):
        return False


def _select_blocking_recipe(profile: RepoProfile) -> dict[str, object] | None:
    if not profile.state_recipes:
        return None
    for recipe in profile.state_recipes:
        if recipe.blocking:
            return recipe.to_dict()
    return profile.state_recipes[0].to_dict()
