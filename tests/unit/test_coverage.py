"""Unit tests for `playwright_god.coverage`."""

from __future__ import annotations

import json
import signal
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from playwright_god import coverage as cov_mod
from playwright_god.coverage import (
    BackendCoverageError,
    CoverageCollector,
    CoverageReport,
    FileCoverage,
    coverage_fixture_path,
    coverage_from_dict,
    coverage_to_dict,
    load_coverage_fixture,
    merge,
    parse_python_coverage_json,
    parse_v8_coverage,
    _line_set_to_ranges,
)


FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "coverage_sample.json"


@pytest.fixture(scope="module")
def sample_payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


class TestLineRanges:
    def test_empty(self):
        assert _line_set_to_ranges([]) == ()

    def test_contiguous(self):
        assert _line_set_to_ranges([3, 4, 5, 7, 8, 11]) == ((3, 5), (7, 8), (11, 11))

    def test_dedup_unsorted(self):
        assert _line_set_to_ranges([2, 1, 2, 3]) == ((1, 3),)


# ---------------------------------------------------------------------------
# v8 parser
# ---------------------------------------------------------------------------


class TestParseV8Coverage:
    def test_parses_url_and_lines(self, sample_payload):
        files = parse_v8_coverage(sample_payload["frontend_v8"])
        assert files
        ((path, fc),) = files.items()
        assert path.endswith("app.js")
        assert fc.total_lines >= 7
        assert fc.covered_lines >= 1
        # logout() (count=0) lines should be in missing ranges
        flat_missing = {n for a, b in fc.missing_line_ranges for n in range(a, b + 1)}
        assert any(line >= 6 for line in flat_missing)

    def test_skips_entries_without_source(self):
        files = parse_v8_coverage([{"url": "x", "functions": []}])
        assert files == {}

    def test_zero_count_ranges_excluded(self):
        payload = [
            {
                "url": "a.js",
                "source": "a\nb\nc\n",
                "functions": [{"ranges": [{"startOffset": 0, "endOffset": 1, "count": 0}]}],
            }
        ]
        files = parse_v8_coverage(payload)
        ((_, fc),) = files.items()
        assert fc.covered_lines == 0


# ---------------------------------------------------------------------------
# python parser
# ---------------------------------------------------------------------------


class TestParsePythonCoverageJson:
    def test_basic(self, sample_payload):
        files = parse_python_coverage_json(sample_payload["backend_python"])
        assert "src/api/users.py" in files
        users = files["src/api/users.py"]
        assert users.total_lines == 7
        assert users.covered_lines == 4
        assert users.missing_line_ranges == ((3, 3), (5, 6))

    def test_empty_payload(self):
        assert parse_python_coverage_json({}) == {}

    def test_invalid_entry_skipped(self):
        out = parse_python_coverage_json({"files": {"a.py": "broken"}})
        assert out == {}


# ---------------------------------------------------------------------------
# merging + serialization
# ---------------------------------------------------------------------------


def _fc(path: str, total: int, covered: list[int]) -> FileCoverage:
    cov_set = frozenset(covered)
    missing = sorted(set(range(1, total + 1)) - cov_set)
    return FileCoverage(
        path=path,
        total_lines=total,
        covered_lines=len(cov_set),
        missing_line_ranges=_line_set_to_ranges(missing),
        covered_line_set=cov_set,
    )


class TestMerge:
    def test_union_overlapping_files(self):
        f = CoverageReport(source="frontend", files={"a.ts": _fc("a.ts", 5, [1, 2])}, generated_at="t")
        b = CoverageReport(source="backend", files={"a.ts": _fc("a.ts", 5, [3, 4])}, generated_at="t")
        m = merge(f, b)
        assert m.source == "merged"
        assert m.merge_meta == ("frontend", "backend")
        assert m.files["a.ts"].covered_lines == 4
        assert m.files["a.ts"].covered_line_set == frozenset({1, 2, 3, 4})

    def test_unique_files_concatenated(self):
        f = CoverageReport(source="frontend", files={"a.ts": _fc("a.ts", 3, [1])}, generated_at="t")
        b = CoverageReport(source="backend", files={"b.py": _fc("b.py", 2, [1, 2])}, generated_at="t")
        m = merge(f, b)
        assert set(m.files) == {"a.ts", "b.py"}

    def test_only_one_side(self):
        f = CoverageReport(source="frontend", files={"a.ts": _fc("a.ts", 3, [1, 2, 3])}, generated_at="t")
        m = merge(f, None)
        assert m.merge_meta == ("frontend",)
        assert m.percent == 100.0


class TestSerialize:
    def test_roundtrip(self):
        rep = CoverageReport(
            source="backend",
            files={"x.py": _fc("x.py", 4, [1, 2])},
            generated_at="2026-04-19T00:00:00+00:00",
        )
        d = coverage_to_dict(rep)
        back = coverage_from_dict(d)
        assert back.source == "backend"
        assert back.files["x.py"].total_lines == 4
        assert back.files["x.py"].covered_lines == 2

    def test_roundtrip_merged(self):
        m = merge(
            CoverageReport(source="frontend", files={"a": _fc("a", 2, [1])}, generated_at="t"),
            CoverageReport(source="backend", files={"a": _fc("a", 2, [2])}, generated_at="t"),
        )
        back = coverage_from_dict(coverage_to_dict(m))
        assert back.source == "merged"
        assert back.merge_meta == ("frontend", "backend")


# ---------------------------------------------------------------------------
# fixture asset loading
# ---------------------------------------------------------------------------


class TestFixtureAsset:
    def test_path_exists(self):
        assert coverage_fixture_path().is_file()

    def test_load_contents(self):
        text = load_coverage_fixture()
        assert "startJSCoverage" in text
        assert "PLAYWRIGHT_GOD_COVERAGE_DIR" in text


# ---------------------------------------------------------------------------
# CoverageCollector
# ---------------------------------------------------------------------------


class TestCoverageCollectorFrontend:
    def test_collect_frontend_basic(self, sample_payload):
        c = CoverageCollector(frontend=True)
        rep = c.collect_frontend(sample_payload["frontend_v8"])
        assert rep.source == "frontend"
        assert rep.total_files == 1

    def test_non_chromium_returns_empty_and_warns(self, sample_payload, caplog):
        c = CoverageCollector(frontend=True)
        with caplog.at_level("WARNING", logger="playwright_god.coverage"):
            rep = c.collect_frontend(sample_payload["frontend_v8"], browser="firefox")
        assert rep.files == {}
        assert any("chromium" in m.lower() for m in caplog.messages)
        # Second call should not warn again.
        caplog.clear()
        c.collect_frontend(sample_payload["frontend_v8"], browser="firefox")
        assert not caplog.messages


class TestCoverageCollectorBackend:
    def test_no_backend_cmd_raises(self):
        c = CoverageCollector()
        with pytest.raises(BackendCoverageError):
            c._resolve_backend_cmd()

    def test_missing_coverage_binary(self, monkeypatch, tmp_path):
        c = CoverageCollector(backend_cmd="myapp", backend_workdir=tmp_path)
        monkeypatch.setattr(cov_mod.shutil, "which", lambda _: None)
        with pytest.raises(BackendCoverageError, match="coverage"):
            c.collect_backend(lambda: None)

    def test_backend_full_pipeline(self, monkeypatch, tmp_path, sample_payload):
        cov_json = tmp_path / ".pg_coverage.json"
        c = CoverageCollector(
            backend_cmd="myapp",
            backend_workdir=tmp_path,
            coverage_json_path=cov_json,
            backend_timeout_s=0.05,
        )
        monkeypatch.setattr(cov_mod.shutil, "which", lambda _: "/usr/bin/coverage")

        # Stub subprocess.run for `coverage erase` and `coverage json -o ...`.
        def fake_run(argv, **kw):
            if "json" in argv:
                cov_json.write_text(json.dumps(sample_payload["backend_python"]))
            return subprocess.CompletedProcess(argv, 0, "", "")

        monkeypatch.setattr(cov_mod.subprocess, "run", fake_run)

        class FakeProc:
            returncode = 0

            def __init__(self):
                self._dead = False

            def poll(self):
                return None if not self._dead else 0

            def send_signal(self, sig):
                self._dead = True

            def terminate(self):
                self._dead = True

            def kill(self):
                self._dead = True

            def wait(self, timeout=None):
                return 0

            stdout = None
            stderr = None

        monkeypatch.setattr(cov_mod.subprocess, "Popen", lambda *a, **kw: FakeProc())
        monkeypatch.setattr(cov_mod.time, "sleep", lambda _: None)

        rep = c.collect_backend(lambda: None)
        assert rep.source == "backend"
        assert "src/api/users.py" in rep.files

    def test_backend_erase_failure(self, monkeypatch, tmp_path):
        c = CoverageCollector(backend_cmd="myapp", backend_workdir=tmp_path)
        monkeypatch.setattr(cov_mod.shutil, "which", lambda _: "/bin/coverage")
        monkeypatch.setattr(
            cov_mod.subprocess,
            "run",
            lambda *a, **kw: subprocess.CompletedProcess(a, 1, "", "boom"),
        )
        with pytest.raises(BackendCoverageError, match="erase"):
            c.collect_backend(lambda: None)


class TestCollectorCombined:
    def test_collect_only_frontend(self, sample_payload):
        c = CoverageCollector(frontend=True)
        called = {"n": 0}

        def fake_run():
            called["n"] += 1

        m = c.collect(fake_run, coverage_raw=sample_payload["frontend_v8"])
        assert called["n"] == 1
        assert m.merge_meta == ("frontend",)


# ---------------------------------------------------------------------------
# Property edge cases
# ---------------------------------------------------------------------------


class TestProperties:
    def test_empty_filecoverage_percent_is_100(self):
        fc = FileCoverage(path="x", total_lines=0, covered_lines=0)
        assert fc.percent == 100.0
        assert fc.uncovered_lines == 0

    def test_empty_report_percent_is_100(self):
        rep = CoverageReport(source="backend", files={}, generated_at="t")
        assert rep.percent == 100.0
        assert rep.total_lines == 0
        assert rep.covered_lines == 0

    def test_coverage_from_dict_non_merged_branch(self):
        from playwright_god.coverage import coverage_from_dict
        rep = coverage_from_dict(
            {
                "source": "frontend",
                "generated_at": "t",
                "files": {"a.ts": {"total_lines": 3, "covered_lines": 1,
                                   "missing_line_ranges": [[2, 3]]}},
            }
        )
        assert rep.source == "frontend"
        assert "a.ts" in rep.files
        assert rep.files["a.ts"].missing_line_ranges == ((2, 3),)

    def test_coverage_from_dict_skips_invalid_entries(self):
        from playwright_god.coverage import coverage_from_dict
        rep = coverage_from_dict({"source": "merged", "files": {"a": "broken"}})
        assert rep.files == {}

    def test_v8_url_strip_branches(self):
        # http:// scheme, https:// scheme, file:// scheme
        urls = ["http://h/a.js", "https://h/b.js", "file:///c/d.js", "/abs.js"]
        payload = [
            {"url": u, "source": "x\n", "functions": []} for u in urls
        ]
        files = parse_v8_coverage(payload)
        assert len(files) == 4


# ---------------------------------------------------------------------------
# Backend collector failure paths
# ---------------------------------------------------------------------------


class TestBackendFailures:
    def _setup(self, monkeypatch, tmp_path):
        monkeypatch.setattr(cov_mod.shutil, "which", lambda _: "/bin/coverage")
        monkeypatch.setattr(cov_mod.time, "sleep", lambda _: None)

    def test_backend_cmd_not_found(self, monkeypatch, tmp_path):
        self._setup(monkeypatch, tmp_path)
        c = CoverageCollector(backend_cmd="missing", backend_workdir=tmp_path)
        monkeypatch.setattr(
            cov_mod.subprocess, "run",
            lambda *a, **kw: subprocess.CompletedProcess(a, 0, "", ""),
        )

        def boom(*a, **kw):
            raise FileNotFoundError("no such binary")

        monkeypatch.setattr(cov_mod.subprocess, "Popen", boom)
        with pytest.raises(BackendCoverageError, match="not found"):
            c.collect_backend(lambda: None)

    def test_backend_dies_immediately(self, monkeypatch, tmp_path):
        self._setup(monkeypatch, tmp_path)
        c = CoverageCollector(backend_cmd="myapp", backend_workdir=tmp_path)
        monkeypatch.setattr(
            cov_mod.subprocess, "run",
            lambda *a, **kw: subprocess.CompletedProcess(a, 0, "", ""),
        )

        class DeadProc:
            returncode = 7
            class _S:
                @staticmethod
                def read():
                    return "boom"
            stderr = _S()
            stdout = None

            def poll(self):
                return 7

        monkeypatch.setattr(cov_mod.subprocess, "Popen", lambda *a, **kw: DeadProc())
        with pytest.raises(BackendCoverageError, match="failed before run"):
            c.collect_backend(lambda: None)

    def test_backend_coverage_json_failure(self, monkeypatch, tmp_path):
        self._setup(monkeypatch, tmp_path)
        cov_json = tmp_path / "out.json"
        c = CoverageCollector(
            backend_cmd="myapp", backend_workdir=tmp_path,
            coverage_json_path=cov_json,
        )

        def fake_run(argv, **kw):
            if "json" in argv:
                return subprocess.CompletedProcess(argv, 1, "", "json oops")
            return subprocess.CompletedProcess(argv, 0, "", "")

        monkeypatch.setattr(cov_mod.subprocess, "run", fake_run)

        class FakeProc:
            returncode = 0
            stdout = stderr = None
            def poll(self): return None
            def send_signal(self, _): pass
            def wait(self, timeout=None): return 0

        monkeypatch.setattr(cov_mod.subprocess, "Popen", lambda *a, **kw: FakeProc())
        with pytest.raises(BackendCoverageError, match="coverage json"):
            c.collect_backend(lambda: None)


class TestTerminate:
    def test_already_dead_no_op(self):
        c = CoverageCollector(backend_cmd="x")
        class P:
            def poll(self): return 0
        c._terminate(P())  # should not raise

    def test_sigint_then_sigterm_then_kill(self):
        c = CoverageCollector(backend_cmd="x", backend_timeout_s=0.01)
        calls = []
        class P:
            def poll(self): return None
            def send_signal(self, sig): calls.append(("int", sig))
            def wait(self, timeout=None):
                calls.append(("wait", timeout))
                raise subprocess.TimeoutExpired("x", timeout)
            def terminate(self): calls.append(("term",))
            def kill(self): calls.append(("kill",))
        c._terminate(P())
        assert ("term",) in calls and ("kill",) in calls

    def test_sigint_send_oserror(self):
        c = CoverageCollector(backend_cmd="x")
        class P:
            def poll(self): return None
            def send_signal(self, sig): raise OSError("nope")
        c._terminate(P())  # swallowed
