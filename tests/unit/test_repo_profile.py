"""Unit tests for repository profiling and inspection support."""

from __future__ import annotations

import json
from pathlib import Path

from playwright_god.crawler import RepositoryCrawler
from playwright_god.extractors import extractor_capabilities
from playwright_god.extractors import extract as extract_flow_graph
from playwright_god.repo_profile import analyze_repository, format_repo_profile, repo_profile_prompt


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_analyze_repository_detects_react_fastapi_stack(tmp_path: Path):
    _write(
        tmp_path / "package.json",
        json.dumps(
            {
                "scripts": {"dev": "vite"},
                "dependencies": {"react": "^18.0.0", "react-router-dom": "^6.0.0"},
                "devDependencies": {"vite": "^5.0.0", "@playwright/test": "^1.0.0"},
            }
        ),
    )
    _write(
        tmp_path / "pyproject.toml",
        """
[project]
name = "demo"
dependencies = ["fastapi", "uvicorn", "pytest"]
""".strip(),
    )
    _write(tmp_path / ".env.example", "TEST_USERNAME=\nTEST_PASSWORD=\n")
    _write(tmp_path / "src" / "App.tsx", "export default function App(){ return null }\n")
    _write(
        tmp_path / "api.py",
        "from fastapi import FastAPI\napp = FastAPI()\n@app.get('/healthz')\ndef x(): return 'ok'\n",
    )

    crawler = RepositoryCrawler()
    files = crawler.crawl(str(tmp_path))
    graph = extract_flow_graph(tmp_path)
    profile = analyze_repository(
        tmp_path,
        files,
        flow_graph=graph,
        extractor_capabilities=extractor_capabilities(),
    )

    assert profile.archetype == "api-plus-frontend"
    assert "react" in profile.frameworks
    assert "fastapi" in profile.frameworks
    assert profile.startup_candidates
    assert profile.runtime_targets
    assert "TEST_USERNAME" in profile.environment_profile["env_vars"]


def test_format_repo_profile_renders_blind_spots(tmp_path: Path):
    _write(tmp_path / "go.mod", "module example.com/demo\nrequire github.com/gin-gonic/gin v1.0.0\n")
    _write(tmp_path / "main.go", "package main\nfunc main(){}\n")
    crawler = RepositoryCrawler()
    files = crawler.crawl(str(tmp_path))
    profile = analyze_repository(
        tmp_path,
        files,
        flow_graph=None,
        extractor_capabilities=extractor_capabilities(),
    )
    rendered = format_repo_profile(profile)
    assert "Blind spots" in rendered
    assert "No first-class surface extractor" in rendered


def test_repo_profile_prompt_contains_high_signal_summary(tmp_path: Path):
    _write(tmp_path / "package.json", json.dumps({"scripts": {"start": "next start"}, "dependencies": {"next": "14.0.0"}}))
    _write(tmp_path / "app" / "page.tsx", "export default function Page(){ return null }\n")
    crawler = RepositoryCrawler()
    files = crawler.crawl(str(tmp_path))
    graph = extract_flow_graph(tmp_path)
    profile = analyze_repository(
        tmp_path,
        files,
        flow_graph=graph,
        extractor_capabilities=extractor_capabilities(),
    )
    prompt = repo_profile_prompt(profile)
    assert "Archetype:" in prompt
    assert "Startup candidates:" in prompt
