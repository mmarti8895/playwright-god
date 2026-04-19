"""Coverage collection for the Playwright runner.

Provides the data shapes (`FileCoverage`, `CoverageReport`, `MergedCoverageReport`)
and the orchestration class (`CoverageCollector`) that brackets a Playwright
run with optional frontend (Chromium JS coverage via a fixture) and backend
(user-supplied subprocess) coverage capture.

The module is deliberately framework-agnostic on the backend side: the user
provides a *start command* (e.g. ``coverage run -m uvicorn app:app``) and the
collector takes care of `coverage erase` before, graceful termination after,
and parsing the resulting ``coverage json`` artifact into a normalized
:class:`CoverageReport`.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import shlex
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal, Mapping, Sequence

logger = logging.getLogger(__name__)

CoverageSource = Literal["frontend", "backend", "merged"]

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class BackendCoverageError(RuntimeError):
    """Raised when the user-supplied backend coverage command fails."""


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FileCoverage:
    """Per-file coverage snapshot."""

    path: str
    total_lines: int
    covered_lines: int
    missing_line_ranges: tuple[tuple[int, int], ...] = ()
    covered_line_set: frozenset[int] = field(default_factory=frozenset)

    @property
    def percent(self) -> float:
        if self.total_lines <= 0:
            return 100.0
        return round(100.0 * self.covered_lines / self.total_lines, 2)

    @property
    def uncovered_lines(self) -> int:
        return max(0, self.total_lines - self.covered_lines)


@dataclass(frozen=True)
class CoverageReport:
    """A single-source coverage report (frontend OR backend)."""

    source: CoverageSource
    files: Mapping[str, FileCoverage]
    generated_at: str

    @property
    def total_files(self) -> int:
        return len(self.files)

    @property
    def total_lines(self) -> int:
        return sum(f.total_lines for f in self.files.values())

    @property
    def covered_lines(self) -> int:
        return sum(f.covered_lines for f in self.files.values())

    @property
    def percent(self) -> float:
        if self.total_lines <= 0:
            return 100.0
        return round(100.0 * self.covered_lines / self.total_lines, 2)


@dataclass(frozen=True)
class MergedCoverageReport(CoverageReport):
    """The line-set union of a frontend and backend report.

    `merge_meta` records the upstream sources that were combined.
    """

    merge_meta: tuple[CoverageSource, ...] = ()
    routes: tuple["RouteCoverage", ...] = ()


@dataclass(frozen=True)
class RouteCoverage:
    """Per-route coverage outcome derived from handler evidence."""

    route_id: str
    method: str
    path: str
    covered: bool
    handler_files: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Helpers / parsing
# ---------------------------------------------------------------------------


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _line_set_to_ranges(lines: Sequence[int]) -> tuple[tuple[int, int], ...]:
    """Compress a sorted list of integers into inclusive (start, end) ranges."""

    ordered = sorted(set(int(l) for l in lines))
    if not ordered:
        return ()
    ranges: list[tuple[int, int]] = []
    start = prev = ordered[0]
    for n in ordered[1:]:
        if n == prev + 1:
            prev = n
            continue
        ranges.append((start, prev))
        start = prev = n
    ranges.append((start, prev))
    return tuple(ranges)


def parse_v8_coverage(payload: Sequence[Mapping]) -> dict[str, FileCoverage]:
    """Parse Playwright's ``page.coverage.stopJSCoverage()`` output.

    Each entry is ``{"url": "...", "source": "...", "functions": [...]}``
    where each function has ``ranges: [{startOffset, endOffset, count}]``.
    For each entry we compute the set of *covered byte offsets* and convert
    them into covered lines using newline positions in ``source``.
    """

    files: dict[str, FileCoverage] = {}
    for entry in payload or ():
        url = entry.get("url") or ""
        source = entry.get("source") or ""
        if not source:
            # No source — we can't map offsets to lines.
            continue
        # Newline indices: line 1 starts at offset 0, line 2 at newlines[0]+1, etc.
        newlines = [i for i, ch in enumerate(source) if ch == "\n"]
        total_lines = len(newlines) + 1

        def offset_to_line(offset: int, _nl: list[int] = newlines) -> int:
            # Binary search would be ideal; linear is fine for small fixtures
            # and Playwright entries.
            line = 1
            for nl in _nl:
                if offset > nl:
                    line += 1
                else:
                    break
            return line

        covered: set[int] = set()
        for fn in entry.get("functions", []) or []:
            for r in fn.get("ranges", []) or []:
                if int(r.get("count", 0)) <= 0:
                    continue
                start = int(r.get("startOffset", 0))
                end = int(r.get("endOffset", start))
                start_line = offset_to_line(start)
                end_line = offset_to_line(max(end - 1, start))
                covered.update(range(start_line, end_line + 1))

        all_lines = set(range(1, total_lines + 1))
        missing = sorted(all_lines - covered)
        # Best-effort path: strip scheme + host.
        path = url
        for prefix in ("http://", "https://", "file://"):
            if path.startswith(prefix):
                path = path[len(prefix):]
                if "/" in path:
                    path = "/" + path.split("/", 1)[1]
                break
        files[path] = FileCoverage(
            path=path,
            total_lines=total_lines,
            covered_lines=len(covered),
            missing_line_ranges=_line_set_to_ranges(missing),
            covered_line_set=frozenset(covered),
        )
    return files


def parse_python_coverage_json(payload: Mapping) -> dict[str, FileCoverage]:
    """Parse the ``coverage json`` format produced by ``coverage>=7``.

    Schema (abbreviated)::

        {
          "files": {
            "src/api/users.py": {
              "executed_lines": [1, 2, 4, 7],
              "missing_lines": [3, 5, 6],
              "summary": {"num_statements": 7, "covered_lines": 4, ...}
            }
          }
        }
    """

    files: dict[str, FileCoverage] = {}
    raw_files = payload.get("files", {}) if isinstance(payload, Mapping) else {}
    for path, entry in raw_files.items():
        if not isinstance(entry, Mapping):
            continue
        executed = entry.get("executed_lines") or []
        missing = entry.get("missing_lines") or []
        summary = entry.get("summary") or {}
        total = int(summary.get("num_statements") or (len(executed) + len(missing)))
        covered = int(summary.get("covered_lines") or len(executed))
        files[path] = FileCoverage(
            path=path,
            total_lines=total,
            covered_lines=covered,
            missing_line_ranges=_line_set_to_ranges(missing),
            covered_line_set=frozenset(int(l) for l in executed),
        )
    return files


# ---------------------------------------------------------------------------
# Merging
# ---------------------------------------------------------------------------


def merge(
    frontend: CoverageReport | None,
    backend: CoverageReport | None,
    *,
    flow_graph: object | None = None,
) -> MergedCoverageReport:
    """Union two single-source reports into a merged one.

    Files unique to either source are concatenated; files present in both have
    their covered-line sets unioned. Totals are recomputed from the merged
    file set.

    When *flow_graph* is supplied (a
    :class:`playwright_god.flow_graph.FlowGraph`), the merged report also
    carries a ``routes`` tuple where each :class:`RouteCoverage` is marked
    covered iff any of its handler-evidence files have at least one covered
    line in the merged file map.
    """

    sources: list[CoverageSource] = []
    paths: set[str] = set()
    if frontend is not None:
        sources.append("frontend")
        paths.update(frontend.files.keys())
    if backend is not None:
        sources.append("backend")
        paths.update(backend.files.keys())

    files: dict[str, FileCoverage] = {}
    for path in sorted(paths):
        f_entry = frontend.files.get(path) if frontend else None
        b_entry = backend.files.get(path) if backend else None
        if f_entry and b_entry:
            covered = set(f_entry.covered_line_set) | set(b_entry.covered_line_set)
            total = max(f_entry.total_lines, b_entry.total_lines)
            all_lines = set(range(1, total + 1))
            missing = sorted(all_lines - covered)
            files[path] = FileCoverage(
                path=path,
                total_lines=total,
                covered_lines=len(covered),
                missing_line_ranges=_line_set_to_ranges(missing),
                covered_line_set=frozenset(covered),
            )
        else:
            files[path] = f_entry or b_entry  # type: ignore[assignment]

    return MergedCoverageReport(
        source="merged",
        files=files,
        generated_at=_now(),
        merge_meta=tuple(sources),
        routes=_route_coverage(flow_graph, files),
    )


def _route_coverage(
    flow_graph: object | None,
    files: Mapping[str, FileCoverage],
) -> tuple[RouteCoverage, ...]:
    """Map flow-graph routes to per-route coverage via handler evidence."""

    if flow_graph is None:
        return ()
    routes_attr = getattr(flow_graph, "routes", None)
    if routes_attr is None:
        return ()
    out: list[RouteCoverage] = []
    for route in routes_attr:
        handler_files: list[str] = []
        for ev in getattr(route, "evidence", ()) or ():
            ev_file = getattr(ev, "file", None)
            if ev_file:
                handler_files.append(ev_file)
        covered = False
        for hf in handler_files:
            fc = files.get(hf)
            if fc is not None and fc.covered_lines > 0:
                covered = True
                break
        out.append(RouteCoverage(
            route_id=route.id,
            method=route.method,
            path=route.path,
            covered=covered,
            handler_files=tuple(dict.fromkeys(handler_files)),
        ))
    return tuple(out)


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def coverage_to_dict(report: CoverageReport) -> dict:
    """Serialize a :class:`CoverageReport` to a JSON-safe dict."""

    payload: dict = {
        "source": report.source,
        "generated_at": report.generated_at,
        "merge_meta": list(getattr(report, "merge_meta", ()) or ()),
        "totals": {
            "total_files": report.total_files,
            "total_lines": report.total_lines,
            "covered_lines": report.covered_lines,
            "percent": report.percent,
        },
        "files": {
            path: {
                "total_lines": fc.total_lines,
                "covered_lines": fc.covered_lines,
                "percent": fc.percent,
                "missing_line_ranges": [list(r) for r in fc.missing_line_ranges],
            }
            for path, fc in report.files.items()
        },
    }
    routes = tuple(getattr(report, "routes", ()) or ())
    if routes:
        covered_ids = sorted(r.route_id for r in routes if r.covered)
        uncovered_ids = sorted(r.route_id for r in routes if not r.covered)
        payload["routes"] = {
            "total": len(routes),
            "covered": covered_ids,
            "uncovered": uncovered_ids,
            "details": [
                {
                    "route_id": r.route_id,
                    "method": r.method,
                    "path": r.path,
                    "covered": r.covered,
                    "handler_files": list(r.handler_files),
                }
                for r in sorted(routes, key=lambda r: r.route_id)
            ],
        }
    return payload


def coverage_from_dict(payload: Mapping) -> CoverageReport:
    """Inverse of :func:`coverage_to_dict`. Returns the right subclass."""

    files = {}
    for path, entry in (payload.get("files") or {}).items():
        if not isinstance(entry, Mapping):
            continue
        ranges = entry.get("missing_line_ranges") or []
        files[path] = FileCoverage(
            path=path,
            total_lines=int(entry.get("total_lines", 0)),
            covered_lines=int(entry.get("covered_lines", 0)),
            missing_line_ranges=tuple(tuple(r) for r in ranges),
        )
    source = payload.get("source", "merged")
    generated_at = payload.get("generated_at") or _now()
    if source == "merged":
        routes_payload = payload.get("routes") or {}
        details = routes_payload.get("details") if isinstance(routes_payload, Mapping) else None
        routes_tuple: tuple[RouteCoverage, ...] = ()
        if details:
            routes_tuple = tuple(
                RouteCoverage(
                    route_id=str(d.get("route_id", "")),
                    method=str(d.get("method", "")),
                    path=str(d.get("path", "")),
                    covered=bool(d.get("covered", False)),
                    handler_files=tuple(d.get("handler_files") or ()),
                )
                for d in details
                if isinstance(d, Mapping)
            )
        return MergedCoverageReport(
            source="merged",
            files=files,
            generated_at=generated_at,
            merge_meta=tuple(payload.get("merge_meta") or ()),
            routes=routes_tuple,
        )
    return CoverageReport(source=source, files=files, generated_at=generated_at)


# ---------------------------------------------------------------------------
# Asset loading (frontend fixture)
# ---------------------------------------------------------------------------


_ASSETS_DIR = Path(__file__).resolve().parent / "_assets"
COVERAGE_FIXTURE_NAME = "coverage_fixture.ts"


def coverage_fixture_path() -> Path:
    """Return the absolute path to the bundled JS coverage fixture."""

    return _ASSETS_DIR / COVERAGE_FIXTURE_NAME


def load_coverage_fixture() -> str:
    """Read the bundled JS coverage fixture as a string."""

    return coverage_fixture_path().read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# CoverageCollector
# ---------------------------------------------------------------------------


@dataclass
class CoverageCollector:
    """Orchestrates frontend + backend coverage capture around a callable.

    Parameters
    ----------
    frontend:
        When True, the run is expected to produce raw V8 coverage payload
        (typically supplied via ``RunResult.coverage_raw``).
    backend_cmd:
        Optional shell-style command (or argv list) that starts the backend
        in coverage mode (e.g. ``"coverage run -m uvicorn app:app --port 8000"``).
        When provided, the collector will erase prior data, start the process,
        invoke the wrapped run, terminate the process, and parse the resulting
        ``coverage json`` output.
    backend_workdir:
        Working directory for the backend command. Defaults to the current dir.
    backend_timeout_s:
        Seconds to wait after SIGINT before sending SIGTERM. Default 10.
    coverage_json_path:
        Destination for ``coverage json -o ...``. Defaults to
        ``<backend_workdir>/.pg_coverage.json``.
    """

    frontend: bool = False
    backend_cmd: str | Sequence[str] | None = None
    backend_workdir: str | os.PathLike | None = None
    backend_timeout_s: float = 10.0
    coverage_json_path: str | os.PathLike | None = None
    chromium_only_warned: bool = field(default=False, init=False, repr=False)

    # ---- frontend ----------------------------------------------------------
    def collect_frontend(
        self,
        coverage_raw: Sequence[Mapping] | None,
        *,
        browser: str | None = "chromium",
    ) -> CoverageReport:
        """Build a frontend :class:`CoverageReport` from raw V8 payload."""

        if browser and browser.lower() != "chromium":
            if not self.chromium_only_warned:
                logger.warning("frontend coverage requires Chromium; got %r", browser)
                self.chromium_only_warned = True
            return CoverageReport(source="frontend", files={}, generated_at=_now())
        files = parse_v8_coverage(coverage_raw or ())
        return CoverageReport(source="frontend", files=files, generated_at=_now())

    # ---- backend -----------------------------------------------------------
    def _resolve_backend_cmd(self) -> list[str]:
        if self.backend_cmd is None:
            raise BackendCoverageError("no backend_cmd configured")
        if isinstance(self.backend_cmd, str):
            return shlex.split(self.backend_cmd)
        return list(self.backend_cmd)

    def _resolve_workdir(self) -> Path:
        return Path(self.backend_workdir) if self.backend_workdir else Path.cwd()

    def _resolve_coverage_json(self) -> Path:
        if self.coverage_json_path:
            return Path(self.coverage_json_path)
        return self._resolve_workdir() / ".pg_coverage.json"

    def collect_backend(self, run_callable: Callable[[], object]) -> CoverageReport:
        """Bracket ``run_callable`` with backend coverage capture.

        Steps:
            1. ``coverage erase``
            2. start backend command (background)
            3. call run_callable
            4. SIGINT then SIGTERM after ``backend_timeout_s``
            5. ``coverage json -o <path>``
            6. parse and return :class:`CoverageReport`
        """

        argv = self._resolve_backend_cmd()
        workdir = self._resolve_workdir()
        out_path = self._resolve_coverage_json()
        coverage_bin = shutil.which("coverage")
        if coverage_bin is None:
            raise BackendCoverageError(
                "`coverage` not found on PATH; install with `pip install coverage`"
            )

        # 1. erase
        erase = subprocess.run(
            [coverage_bin, "erase"],
            cwd=str(workdir),
            capture_output=True,
            text=True,
            check=False,
        )
        if erase.returncode != 0:
            raise BackendCoverageError(
                f"`coverage erase` failed (exit {erase.returncode}): "
                f"{erase.stderr.strip()[:400]}"
            )

        # 2. start backend
        try:
            proc = subprocess.Popen(  # noqa: S603 — argv list, no shell
                argv,
                cwd=str(workdir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except FileNotFoundError as exc:
            raise BackendCoverageError(
                f"backend command not found: {argv[0]} ({exc})"
            ) from exc

        # Give the backend a brief moment to either die or start serving.
        time.sleep(0.1)
        if proc.poll() is not None and proc.returncode != 0:
            stderr_tail = (proc.stderr.read() if proc.stderr else "") or ""
            raise BackendCoverageError(
                f"backend command failed before run: {' '.join(argv)} "
                f"(exit {proc.returncode}): {stderr_tail.strip()[:400]}"
            )

        # 3. wrapped run
        try:
            run_callable()
        finally:
            # 4. graceful stop: SIGINT then SIGTERM
            self._terminate(proc)

        # 5. coverage json
        out_path.parent.mkdir(parents=True, exist_ok=True)
        json_proc = subprocess.run(
            [coverage_bin, "json", "-o", str(out_path)],
            cwd=str(workdir),
            capture_output=True,
            text=True,
            check=False,
        )
        if json_proc.returncode != 0 or not out_path.is_file():
            raise BackendCoverageError(
                f"`coverage json` failed (exit {json_proc.returncode}): "
                f"{json_proc.stderr.strip()[:400]}"
            )

        try:
            payload = json.loads(out_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BackendCoverageError(
                f"could not parse coverage JSON at {out_path}: {exc}"
            ) from exc

        files = parse_python_coverage_json(payload)
        if not files:
            logger.warning("backend coverage produced 0 files; check backend_cmd")
        return CoverageReport(source="backend", files=files, generated_at=_now())

    # ---- public combined API ----------------------------------------------
    def collect(
        self,
        run_callable: Callable[[], object],
        *,
        coverage_raw: Sequence[Mapping] | None = None,
        browser: str | None = "chromium",
    ) -> MergedCoverageReport:
        """Run the full collection pipeline and return a merged report.

        If only one source is enabled, the merged report still has one entry
        per file and a ``merge_meta`` recording which sources were active.
        """

        frontend_report: CoverageReport | None = None
        backend_report: CoverageReport | None = None

        if self.backend_cmd is not None:
            backend_report = self.collect_backend(run_callable)
        else:
            run_callable()

        if self.frontend:
            frontend_report = self.collect_frontend(coverage_raw, browser=browser)

        return merge(frontend_report, backend_report)

    # ---- internals --------------------------------------------------------
    def _terminate(self, proc: subprocess.Popen) -> None:
        if proc.poll() is not None:
            return
        try:
            proc.send_signal(signal.SIGINT)
        except (ProcessLookupError, OSError):
            return
        try:
            proc.wait(timeout=self.backend_timeout_s)
            return
        except subprocess.TimeoutExpired:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=self.backend_timeout_s)
        except (ProcessLookupError, OSError, subprocess.TimeoutExpired):
            try:
                proc.kill()
            except (ProcessLookupError, OSError):
                pass


__all__ = [
    "BackendCoverageError",
    "CoverageCollector",
    "CoverageReport",
    "FileCoverage",
    "MergedCoverageReport",
    "RouteCoverage",
    "coverage_fixture_path",
    "coverage_from_dict",
    "coverage_to_dict",
    "load_coverage_fixture",
    "merge",
    "parse_python_coverage_json",
    "parse_v8_coverage",
]
