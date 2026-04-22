"""Repository profiling and lightweight runtime/discovery support.

This module provides the first-pass repository understanding layer used by the
`inspect` and `discover` CLI commands. It intentionally favours breadth and
best-effort inference over perfect stack-specific precision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import time
import tomllib
from typing import Any, Iterable, Sequence
from urllib import error, request

from .crawler import FileInfo


SUPPORTED_SURFACE_LANGUAGES = frozenset({"python", "javascript", "typescript", "html", "vue"})


@dataclass(frozen=True)
class BlindSpot:
    category: str
    summary: str
    confidence: float = 0.5

    def to_dict(self) -> dict[str, object]:
        return {
            "category": self.category,
            "summary": self.summary,
            "confidence": round(self.confidence, 3),
        }


@dataclass(frozen=True)
class StartupCandidate:
    command: str
    source: str
    working_dir: str = "."
    base_url: str | None = None
    confidence: float = 0.5

    def to_dict(self) -> dict[str, object]:
        return {
            "command": self.command,
            "source": self.source,
            "working_dir": self.working_dir,
            "base_url": self.base_url,
            "confidence": round(self.confidence, 3),
        }


@dataclass(frozen=True)
class RuntimeTarget:
    kind: str
    path: str
    method: str = "GET"
    base_url: str | None = None
    source: str = "inferred"
    confidence: float = 0.5

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "path": self.path,
            "method": self.method,
            "base_url": self.base_url,
            "source": self.source,
            "confidence": round(self.confidence, 3),
        }


@dataclass(frozen=True)
class StateRecipe:
    title: str
    steps: tuple[str, ...]
    confidence: float = 0.5
    kind: str = "generic"
    required_env: tuple[str, ...] = ()
    blocking: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "title": self.title,
            "steps": list(self.steps),
            "confidence": round(self.confidence, 3),
            "kind": self.kind,
            "required_env": list(self.required_env),
            "blocking": self.blocking,
        }


@dataclass(frozen=True)
class RepoProfile:
    source_root: str
    languages: dict[str, int]
    frameworks: tuple[str, ...] = ()
    package_managers: tuple[str, ...] = ()
    build_tools: tuple[str, ...] = ()
    test_frameworks: tuple[str, ...] = ()
    archetype: str = "unknown"
    confidence: float = 0.5
    startup_candidates: tuple[StartupCandidate, ...] = ()
    runtime_targets: tuple[RuntimeTarget, ...] = ()
    auth_profile: dict[str, object] = field(default_factory=dict)
    environment_profile: dict[str, object] = field(default_factory=dict)
    bootstrap_steps: tuple[str, ...] = ()
    state_recipes: tuple[StateRecipe, ...] = ()
    blind_spots: tuple[BlindSpot, ...] = ()
    notes: tuple[str, ...] = ()
    runtime_profile: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "source_root": self.source_root,
            "languages": self.languages,
            "frameworks": list(self.frameworks),
            "package_managers": list(self.package_managers),
            "build_tools": list(self.build_tools),
            "test_frameworks": list(self.test_frameworks),
            "archetype": self.archetype,
            "confidence": round(self.confidence, 3),
            "startup_candidates": [item.to_dict() for item in self.startup_candidates],
            "runtime_targets": [item.to_dict() for item in self.runtime_targets],
            "auth_profile": self.auth_profile,
            "environment_profile": self.environment_profile,
            "bootstrap_steps": list(self.bootstrap_steps),
            "state_recipes": [item.to_dict() for item in self.state_recipes],
            "blind_spots": [item.to_dict() for item in self.blind_spots],
            "notes": list(self.notes),
            "runtime_profile": self.runtime_profile,
        }


@dataclass(frozen=True)
class RuntimeProbeResult:
    attempted: bool
    startup_candidate: StartupCandidate | None = None
    reachable: tuple[str, ...] = ()
    unreachable: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "attempted": self.attempted,
            "startup_candidate": (
                self.startup_candidate.to_dict() if self.startup_candidate is not None else None
            ),
            "reachable": list(self.reachable),
            "unreachable": list(self.unreachable),
            "notes": list(self.notes),
        }


def analyze_repository(
    root: str | Path,
    files: Sequence[FileInfo],
    *,
    flow_graph: object | None = None,
    extractor_capabilities: Sequence[dict[str, object]] | None = None,
) -> RepoProfile:
    """Infer a repository profile from crawled files and optional flow graph."""

    root_path = Path(root).resolve()
    languages = _language_counts(files)
    manifest_map = {file.path: file for file in files}
    lower_paths = {file.path.lower() for file in files}
    combined_text = "\n".join(file.content[:2000] for file in files[:80]).lower()

    frameworks = _detect_frameworks(manifest_map, combined_text)
    package_managers = _detect_package_managers(lower_paths)
    build_tools = _detect_build_tools(manifest_map, frameworks)
    test_frameworks = _detect_test_frameworks(manifest_map, lower_paths)
    archetype = _classify_archetype(frameworks, lower_paths, flow_graph)
    startup_candidates = _startup_candidates(root_path, manifest_map, frameworks)
    runtime_targets = _runtime_targets(flow_graph, startup_candidates)
    auth_profile = _auth_profile(files)
    environment_profile = _environment_profile(files)
    bootstrap_steps = _bootstrap_steps(startup_candidates, environment_profile)
    state_recipes = _state_recipes(auth_profile, environment_profile)
    blind_spots = _blind_spots(
        languages=languages,
        frameworks=frameworks,
        startup_candidates=startup_candidates,
        extractor_capabilities=extractor_capabilities or (),
    )
    confidence = _confidence_score(
        frameworks=frameworks,
        startup_candidates=startup_candidates,
        runtime_targets=runtime_targets,
        blind_spots=blind_spots,
    )
    notes = _notes(frameworks, archetype, auth_profile, environment_profile)

    return RepoProfile(
        source_root=str(root_path),
        languages=languages,
        frameworks=frameworks,
        package_managers=package_managers,
        build_tools=build_tools,
        test_frameworks=test_frameworks,
        archetype=archetype,
        confidence=confidence,
        startup_candidates=startup_candidates,
        runtime_targets=runtime_targets,
        auth_profile=auth_profile,
        environment_profile=environment_profile,
        bootstrap_steps=bootstrap_steps,
        state_recipes=state_recipes,
        blind_spots=blind_spots,
        notes=notes,
        runtime_profile={},
    )


def format_repo_profile(profile: RepoProfile, *, runtime_probe: RuntimeProbeResult | None = None) -> str:
    """Render a human-readable repo profile summary."""

    lines = [
        "Repository inspection",
        "=====================",
        f"Root         : {profile.source_root}",
        f"Archetype    : {profile.archetype}",
        f"Confidence   : {profile.confidence:.2f}",
        f"Languages    : {_format_counts(profile.languages)}",
        f"Frameworks   : {', '.join(profile.frameworks) or 'n/a'}",
        f"Pkg managers : {', '.join(profile.package_managers) or 'n/a'}",
        f"Build tools  : {', '.join(profile.build_tools) or 'n/a'}",
        f"Test fwks    : {', '.join(profile.test_frameworks) or 'n/a'}",
        "",
        "Startup candidates",
        "------------------",
    ]
    if profile.startup_candidates:
        for item in profile.startup_candidates[:8]:
            base_url = f" -> {item.base_url}" if item.base_url else ""
            lines.append(
                f"- [{item.confidence:.2f}] `{item.command}` ({item.source}, cwd={item.working_dir}){base_url}"
            )
    else:
        lines.append("- none inferred")

    lines.extend(["", "Runtime targets", "---------------"])
    if profile.runtime_targets:
        for target in profile.runtime_targets[:12]:
            base = target.base_url or "(base unknown)"
            lines.append(
                f"- [{target.confidence:.2f}] {target.method} {target.path} ({target.kind}, {base}, {target.source})"
            )
    else:
        lines.append("- none inferred")

    lines.extend(["", "Environment & auth", "------------------"])
    env_vars = profile.environment_profile.get("env_vars") or []
    auth_signals = profile.auth_profile.get("signals") or []
    lines.append(
        f"- Auth type: {profile.auth_profile.get('type', 'unknown')} "
        f"(confidence={profile.auth_profile.get('confidence', 0.0):.2f})"
    )
    if auth_signals:
        lines.append(f"- Auth signals: {', '.join(str(s) for s in auth_signals[:6])}")
    lines.append(f"- Env vars: {', '.join(str(v) for v in env_vars[:8]) or 'none detected'}")

    if profile.state_recipes:
        lines.extend(["", "State recipes", "-------------"])
        for recipe in profile.state_recipes[:6]:
            steps = "; ".join(recipe.steps)
            lines.append(f"- [{recipe.confidence:.2f}] {recipe.title}: {steps}")

    if profile.blind_spots:
        lines.extend(["", "Blind spots", "-----------"])
        for spot in profile.blind_spots[:10]:
            lines.append(f"- [{spot.confidence:.2f}] {spot.category}: {spot.summary}")

    if runtime_probe is not None:
        lines.extend(["", "Runtime probe", "-------------"])
        lines.append(f"- Attempted: {'yes' if runtime_probe.attempted else 'no'}")
        if runtime_probe.startup_candidate is not None:
            lines.append(f"- Startup: `{runtime_probe.startup_candidate.command}`")
        if runtime_probe.reachable:
            lines.append(f"- Reachable: {', '.join(runtime_probe.reachable)}")
        if runtime_probe.unreachable:
            lines.append(f"- Unreachable: {', '.join(runtime_probe.unreachable)}")
        for note in runtime_probe.notes:
            lines.append(f"- Note: {note}")

    return "\n".join(lines)


def repo_profile_prompt(profile: RepoProfile) -> str:
    """Return a compact prompt-friendly repo profile block."""

    parts = [
        "Repository profile",
        "------------------",
        f"Archetype: {profile.archetype} (confidence={profile.confidence:.2f})",
        f"Frameworks: {', '.join(profile.frameworks) or 'n/a'}",
        f"Startup candidates: {', '.join(item.command for item in profile.startup_candidates[:4]) or 'n/a'}",
        f"Auth type: {profile.auth_profile.get('type', 'unknown')}",
        f"Environment vars: {', '.join(str(v) for v in (profile.environment_profile.get('env_vars') or [])[:8]) or 'n/a'}",
    ]
    if profile.runtime_targets:
        parts.append(
            "Runtime targets: "
            + ", ".join(f"{item.method} {item.path}" for item in profile.runtime_targets[:8])
        )
    if profile.blind_spots:
        parts.append(
            "Blind spots: " + "; ".join(item.summary for item in profile.blind_spots[:6])
        )
    return "\n".join(parts)


def probe_runtime(
    root: str | Path,
    profile: RepoProfile,
    *,
    timeout_seconds: float = 8.0,
) -> RuntimeProbeResult:
    """Best-effort runtime probe: auto-start the top candidate and probe URLs."""

    if not profile.startup_candidates:
        return RuntimeProbeResult(
            attempted=False,
            notes=("No startup candidates inferred.",),
        )

    candidate = profile.startup_candidates[0]
    proc: subprocess.Popen[str] | None = None
    notes: list[str] = []
    root_path = Path(root).resolve()
    cwd = root_path / candidate.working_dir if candidate.working_dir != "." else root_path
    command_parts = shlex.split(candidate.command)
    if not command_parts:
        return RuntimeProbeResult(
            attempted=False,
            startup_candidate=candidate,
            notes=("Startup command was empty after parsing.",),
        )

    try:
        proc = subprocess.Popen(
            command_parts,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except (OSError, ValueError) as exc:
        return RuntimeProbeResult(
            attempted=True,
            startup_candidate=candidate,
            notes=(f"Could not start {candidate.command!r}: {exc}",),
        )

    try:
        urls = _probe_urls(profile)
        reachable: list[str] = []
        unreachable = list(urls)
        start = time.time()
        while time.time() - start < timeout_seconds and unreachable:
            pending: list[str] = []
            for url in unreachable:
                if _url_ok(url):
                    reachable.append(url)
                else:
                    pending.append(url)
            if pending and not reachable:
                time.sleep(0.5)
            unreachable = pending
        if reachable:
            notes.append("At least one inferred runtime target responded successfully.")
        if proc.poll() is not None and proc.returncode not in (0, None):
            stderr = ""
            try:
                assert proc.stderr is not None
                stderr = proc.stderr.read(400).strip()
            except OSError:
                stderr = ""
            if stderr:
                notes.append(f"Process exited early: {stderr}")
        return RuntimeProbeResult(
            attempted=True,
            startup_candidate=candidate,
            reachable=tuple(reachable),
            unreachable=tuple(unreachable),
            notes=tuple(notes),
        )
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)


def _language_counts(files: Sequence[FileInfo]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for file in files:
        counts[file.language] = counts.get(file.language, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _detect_frameworks(manifest_map: dict[str, FileInfo], combined_text: str) -> tuple[str, ...]:
    found: list[str] = []

    package_json = manifest_map.get("package.json")
    if package_json is not None:
        try:
            payload = json.loads(package_json.content)
        except json.JSONDecodeError:
            payload = {}
        deps = {
            *list((payload.get("dependencies") or {}).keys()),
            *list((payload.get("devDependencies") or {}).keys()),
        }
        dep_map = {
            "next": "nextjs",
            "react": "react",
            "react-router-dom": "react-router",
            "vue": "vue",
            "nuxt": "nuxt",
            "svelte": "svelte",
            "@angular/core": "angular",
            "@playwright/test": "playwright",
            "cypress": "cypress",
            "vite": "vite",
            "webpack": "webpack",
            "jest": "jest",
            "vitest": "vitest",
            "webdriverio": "webdriverio",
        }
        for dep_name, framework in dep_map.items():
            if dep_name in deps and framework not in found:
                found.append(framework)

    pyproject = manifest_map.get("pyproject.toml")
    if pyproject is not None:
        lower = pyproject.content.lower()
        for needle, framework in (
            ("fastapi", "fastapi"),
            ("django", "django"),
            ("flask", "flask"),
            ("pytest", "pytest"),
            ("playwright", "playwright"),
            ("uvicorn", "uvicorn"),
        ):
            if needle in lower and framework not in found:
                found.append(framework)

    go_mod = manifest_map.get("go.mod")
    if go_mod is not None:
        lower = go_mod.content.lower()
        for needle, framework in (
            ("gin-gonic/gin", "gin"),
            ("labstack/echo", "echo"),
            ("gofiber/fiber", "fiber"),
        ):
            if needle in lower and framework not in found:
                found.append(framework)

    if "rails" in combined_text and "config/routes.rb" in manifest_map and "rails" not in found:
        found.append("rails")
    if "laravel" in combined_text and "composer.json" in manifest_map and "laravel" not in found:
        found.append("laravel")
    if "springframework" in combined_text and "spring" not in found:
        found.append("spring")
    if ".net" in combined_text or "aspnetcore" in combined_text:
        if "aspnet" not in found:
            found.append("aspnet")

    return tuple(found)


def _detect_package_managers(lower_paths: set[str]) -> tuple[str, ...]:
    found: list[str] = []
    markers = (
        ("package-lock.json", "npm"),
        ("pnpm-lock.yaml", "pnpm"),
        ("yarn.lock", "yarn"),
        ("bun.lockb", "bun"),
        ("pyproject.toml", "pip"),
        ("poetry.lock", "poetry"),
        ("requirements.txt", "pip"),
        ("go.mod", "go"),
        ("cargo.toml", "cargo"),
        ("gemfile", "bundler"),
        ("composer.json", "composer"),
        ("pom.xml", "maven"),
        ("build.gradle", "gradle"),
        ("build.gradle.kts", "gradle"),
        ("paket.dependencies", "paket"),
    )
    for marker, label in markers:
        if marker in lower_paths and label not in found:
            found.append(label)
    return tuple(found)


def _detect_build_tools(manifest_map: dict[str, FileInfo], frameworks: Sequence[str]) -> tuple[str, ...]:
    found: list[str] = []
    path_set = {path.lower() for path in manifest_map}
    for marker, label in (
        ("vite.config.ts", "vite"),
        ("vite.config.js", "vite"),
        ("webpack.config.js", "webpack"),
        ("next.config.js", "next"),
        ("next.config.mjs", "next"),
        ("docker-compose.yml", "docker-compose"),
        ("docker-compose.yaml", "docker-compose"),
        ("dockerfile", "docker"),
        ("makefile", "make"),
    ):
        if marker in path_set and label not in found:
            found.append(label)
    for framework in frameworks:
        if framework in {"fastapi", "django", "flask", "react", "nextjs", "vue", "rails"} and framework not in found:
            found.append(framework)
    return tuple(found)


def _detect_test_frameworks(manifest_map: dict[str, FileInfo], lower_paths: set[str]) -> tuple[str, ...]:
    found: list[str] = []
    for marker, label in (
        ("playwright.config.ts", "playwright"),
        ("pytest.ini", "pytest"),
        ("tox.ini", "pytest"),
        ("cypress.config.ts", "cypress"),
        ("wdio.conf.ts", "webdriverio"),
        ("jest.config.js", "jest"),
        ("vitest.config.ts", "vitest"),
    ):
        if marker in lower_paths and label not in found:
            found.append(label)
    for path, file in manifest_map.items():
        lower = file.content.lower()
        for needle, label in (
            ("@playwright/test", "playwright"),
            ("pytest", "pytest"),
            ("selenium", "selenium"),
            ("cypress", "cypress"),
            ("webdriverio", "webdriverio"),
        ):
            if needle in lower and label not in found:
                found.append(label)
        if path.startswith("tests/") and "pytest" not in found and path.endswith(".py"):
            found.append("pytest")
    return tuple(found)


def _classify_archetype(
    frameworks: Sequence[str],
    lower_paths: set[str],
    flow_graph: object | None,
) -> str:
    has_frontend = any(name in frameworks for name in ("react", "nextjs", "vue", "angular", "svelte"))
    has_backend = any(name in frameworks for name in ("fastapi", "django", "flask", "rails", "spring", "aspnet", "gin", "echo", "fiber"))
    if "apps/" in "".join(sorted(lower_paths)) or "packages/" in "".join(sorted(lower_paths)):
        return "microservice-workspace"
    if has_frontend and has_backend:
        return "api-plus-frontend"
    if "nextjs" in frameworks:
        return "ssr-app"
    if has_frontend:
        return "spa"
    if has_backend:
        return "monolith"
    if any(path.endswith((".html", ".htm")) for path in lower_paths):
        return "static-site"
    routes = tuple(getattr(flow_graph, "routes", ()) or ())
    if routes and not has_frontend:
        return "api-service"
    if "mkdocs.yml" in lower_paths or "docs/" in "".join(sorted(lower_paths)):
        return "docs-site"
    return "unknown"


def _startup_candidates(
    root: Path,
    manifest_map: dict[str, FileInfo],
    frameworks: Sequence[str],
) -> tuple[StartupCandidate, ...]:
    candidates: list[StartupCandidate] = []

    package_json = manifest_map.get("package.json")
    if package_json is not None:
        try:
            payload = json.loads(package_json.content)
        except json.JSONDecodeError:
            payload = {}
        scripts = payload.get("scripts") or {}
        if isinstance(scripts, dict):
            for name, default_url in (
                ("dev", "http://localhost:3000"),
                ("start", "http://localhost:3000"),
                ("serve", "http://localhost:4173"),
                ("preview", "http://localhost:4173"),
            ):
                cmd = scripts.get(name)
                if isinstance(cmd, str) and cmd.strip():
                    runner = "npm run"
                    if (root / "pnpm-lock.yaml").exists():
                        runner = "pnpm"
                        command = f"pnpm {name}"
                    elif (root / "yarn.lock").exists():
                        runner = "yarn"
                        command = f"yarn {name}"
                    else:
                        command = f"{runner} {name}"
                    candidates.append(
                        StartupCandidate(
                            command=command,
                            source=f"package.json:{name}",
                            confidence=0.9 if name in {"dev", "start"} else 0.75,
                            base_url=default_url,
                        )
                    )

    pyproject = manifest_map.get("pyproject.toml")
    if pyproject is not None:
        lower = pyproject.content.lower()
        if "uvicorn" in lower:
            module = _guess_python_app_module(manifest_map)
            candidates.append(
                StartupCandidate(
                    command=f"python -m uvicorn {module}",
                    source="pyproject:uvicorn",
                    confidence=0.7,
                    base_url="http://127.0.0.1:8000",
                )
            )
        if "flask" in lower:
            candidates.append(
                StartupCandidate(
                    command="flask run",
                    source="pyproject:flask",
                    confidence=0.65,
                    base_url="http://127.0.0.1:5000",
                )
            )

    if "manage.py" in manifest_map:
        candidates.append(
            StartupCandidate(
                command="python manage.py runserver 127.0.0.1:8000",
                source="django:manage.py",
                confidence=0.9,
                base_url="http://127.0.0.1:8000",
            )
        )

    if "go.mod" in manifest_map:
        candidates.append(
            StartupCandidate(
                command="go run .",
                source="go.mod",
                confidence=0.6,
                base_url="http://127.0.0.1:8080",
            )
        )

    if "cargo.toml" in {path.lower() for path in manifest_map}:
        candidates.append(
            StartupCandidate(
                command="cargo run",
                source="Cargo.toml",
                confidence=0.55,
                base_url="http://127.0.0.1:3000",
            )
        )

    if "rails" in frameworks:
        candidates.append(
            StartupCandidate(
                command="bundle exec rails server",
                source="rails",
                confidence=0.75,
                base_url="http://127.0.0.1:3000",
            )
        )

    if "aspnet" in frameworks:
        candidates.append(
            StartupCandidate(
                command="dotnet run",
                source="aspnet",
                confidence=0.65,
                base_url="http://127.0.0.1:5000",
            )
        )

    deduped: list[StartupCandidate] = []
    seen: set[tuple[str, str]] = set()
    for candidate in candidates:
        key = (candidate.command, candidate.working_dir)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return tuple(deduped)


def _runtime_targets(
    flow_graph: object | None,
    startup_candidates: Sequence[StartupCandidate],
) -> tuple[RuntimeTarget, ...]:
    base_url = startup_candidates[0].base_url if startup_candidates else None
    targets: list[RuntimeTarget] = []
    routes = tuple(getattr(flow_graph, "routes", ()) or ())
    for route in routes[:16]:
        targets.append(
            RuntimeTarget(
                kind="route",
                method=getattr(route, "method", "GET"),
                path=getattr(route, "path", "/"),
                base_url=base_url,
                source="flow-graph",
                confidence=0.8,
            )
        )
    if not targets and base_url:
        targets.append(
            RuntimeTarget(
                kind="app-root",
                method="GET",
                path="/",
                base_url=base_url,
                source="startup-candidate",
                confidence=0.55,
            )
        )
    return tuple(targets)


def _auth_profile(files: Sequence[FileInfo]) -> dict[str, object]:
    signals: list[str] = []
    score_map = {
        "saml": 0,
        "oidc": 0,
        "basic": 0,
        "token": 0,
        "none": 0,
    }
    for file in files:
        text = file.content.lower()
        path = file.path.lower()
        for key, words in (
            ("saml", ("saml", "idp", "assertion consumer", "metadata.xml")),
            ("oidc", ("oidc", "oauth", "openid", "auth0")),
            ("basic", ("basic auth", "httpcredentials", "login", "password")),
            ("token", ("api key", "bearer ", "jwt", "token")),
        ):
            for word in words:
                if word in text or word in path:
                    score_map[key] += 1
                    if len(signals) < 8:
                        signals.append(word)
    auth_type = max(("saml", "oidc", "token", "basic"), key=lambda key: score_map[key])
    raw = score_map[auth_type]
    if raw == 0:
        auth_type = "unknown"
    confidence = min(0.95, 0.35 + raw * 0.12) if raw else 0.25
    return {
        "type": auth_type,
        "confidence": round(confidence, 3),
        "signals": signals,
    }


def _environment_profile(files: Sequence[FileInfo]) -> dict[str, object]:
    env_vars: list[str] = []
    seed_signals: list[str] = []
    for file in files:
        path = file.path.lower()
        if path.endswith((".env.example", ".env.sample", ".env.template", ".env")):
            for line in file.content.splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key = line.split("=", 1)[0].strip()
                if key and key not in env_vars:
                    env_vars.append(key)
        lower = file.content.lower()
        for word in ("seed", "fixture", "factory", "reset", "bootstrap"):
            if word in lower or word in path:
                if file.path not in seed_signals:
                    seed_signals.append(file.path)
    return {
        "env_vars": env_vars,
        "seed_signals": seed_signals[:12],
    }


def _bootstrap_steps(
    startup_candidates: Sequence[StartupCandidate],
    environment_profile: dict[str, object],
) -> tuple[str, ...]:
    steps: list[str] = []
    if startup_candidates:
        steps.append(f"Start the app with `{startup_candidates[0].command}`.")
    env_vars = environment_profile.get("env_vars") or []
    if env_vars:
        steps.append(
            "Provide environment variables: " + ", ".join(str(v) for v in env_vars[:8]) + "."
        )
    if environment_profile.get("seed_signals"):
        steps.append("Run seed/bootstrap scripts if the app requires initial state.")
    return tuple(steps)


def _state_recipes(
    auth_profile: dict[str, object],
    environment_profile: dict[str, object],
) -> tuple[StateRecipe, ...]:
    recipes: list[StateRecipe] = []
    auth_type = str(auth_profile.get("type", "unknown"))
    env_vars = tuple(str(item) for item in (environment_profile.get("env_vars") or ()))
    credential_vars = tuple(
        name for name in env_vars if any(token in name.upper() for token in ("USER", "PASS", "TOKEN", "KEY"))
    )
    if auth_type in {"basic", "oidc", "saml", "token"}:
        recipes.append(
            StateRecipe(
                title="Authenticate before protected flows",
                steps=(
                    "Load credentials from environment variables.",
                    "Establish session or token using the repo's auth flow.",
                    "Persist auth state for follow-up journeys when practical.",
                ),
                confidence=float(auth_profile.get("confidence", 0.5)),
                kind="auth-bootstrap",
                required_env=credential_vars,
                blocking=bool(credential_vars),
            )
        )
    if environment_profile.get("seed_signals"):
        recipes.append(
            StateRecipe(
                title="Prepare deterministic test state",
                steps=(
                    "Run seed or fixture setup before the test session.",
                    "Reset shared data after destructive flows when needed.",
                ),
                confidence=0.65,
                kind="state-seed",
            )
        )
    return tuple(recipes)


def _blind_spots(
    *,
    languages: dict[str, int],
    frameworks: Sequence[str],
    startup_candidates: Sequence[StartupCandidate],
    extractor_capabilities: Sequence[dict[str, object]],
) -> tuple[BlindSpot, ...]:
    spots: list[BlindSpot] = []
    supported = set()
    for item in extractor_capabilities:
        if not isinstance(item, dict):
            continue
        for language in item.get("languages", []) or []:
            supported.add(str(language))
    unsupported_languages = sorted(
        language for language, count in languages.items()
        if count > 0 and language not in supported and language not in {"json", "yaml", "markdown", "toml", "xml", "text", "css", "shell"}
    )
    for language in unsupported_languages[:8]:
        spots.append(
            BlindSpot(
                category="extractor",
                summary=f"No first-class surface extractor is registered for {language}.",
                confidence=0.8,
            )
        )
    if not startup_candidates:
        spots.append(
            BlindSpot(
                category="runtime",
                summary="No startup candidate was inferred; runtime discovery may need manual hints.",
                confidence=0.7,
            )
        )
    if frameworks and not any(name in frameworks for name in ("playwright", "pytest", "cypress", "selenium", "webdriverio")):
        spots.append(
            BlindSpot(
                category="tests",
                summary="No existing browser test framework was detected for de-duplication or repair workflows.",
                confidence=0.55,
            )
        )
    return tuple(spots)


def _confidence_score(
    *,
    frameworks: Sequence[str],
    startup_candidates: Sequence[StartupCandidate],
    runtime_targets: Sequence[RuntimeTarget],
    blind_spots: Sequence[BlindSpot],
) -> float:
    score = 0.25
    score += min(len(frameworks), 3) * 0.12
    score += min(len(startup_candidates), 2) * 0.15
    score += min(len(runtime_targets), 4) * 0.07
    score -= min(len(blind_spots), 4) * 0.06
    return round(max(0.1, min(0.95, score)), 3)


def _notes(
    frameworks: Sequence[str],
    archetype: str,
    auth_profile: dict[str, object],
    environment_profile: dict[str, object],
) -> tuple[str, ...]:
    notes: list[str] = [f"Inferred archetype: {archetype}."]
    if frameworks:
        notes.append("Detected frameworks: " + ", ".join(frameworks[:6]) + ".")
    if auth_profile.get("type") not in (None, "unknown"):
        notes.append(f"Authentication appears to use {auth_profile.get('type')}.")
    if environment_profile.get("env_vars"):
        notes.append("Repository exposes environment-variable based configuration.")
    return tuple(notes)


def _guess_python_app_module(manifest_map: dict[str, FileInfo]) -> str:
    for candidate in ("main.py", "app.py", "api.py"):
        if candidate in manifest_map:
            return candidate[:-3] + ":app"
    return "app:app"


def _format_counts(counts: dict[str, int]) -> str:
    return ", ".join(f"{lang} ({count})" for lang, count in counts.items()) or "n/a"


def _probe_urls(profile: RepoProfile) -> list[str]:
    urls: list[str] = []
    for target in profile.runtime_targets[:8]:
        if target.base_url:
            urls.append(target.base_url.rstrip("/") + target.path)
    if not urls:
        for candidate in profile.startup_candidates[:2]:
            if candidate.base_url:
                urls.append(candidate.base_url.rstrip("/") + "/")
    return list(dict.fromkeys(urls))


def _url_ok(url: str) -> bool:
    try:
        req = request.Request(url, method="GET")
        with request.urlopen(req, timeout=1.5) as response:
            return 200 <= getattr(response, "status", 0) < 500
    except (error.URLError, ValueError):
        return False
