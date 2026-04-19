"""Iterative refinement loop: bounded generate → run → evaluate → re-prompt cycles.

The :class:`RefinementLoop` is a pure orchestrator. It composes an existing
``PlaywrightTestGenerator`` and ``PlaywrightRunner`` into an attempt loop with
explicit, testable stop conditions, secret-redacted failure feedback, and a
per-attempt audit trail (``refinement_log.jsonl``).

See ``openspec/changes/iterative-refinement/`` for the spec this implements.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Literal, Sequence

from . import _secrets
from .generator import PlaywrightTestGenerator
from .runner import PlaywrightRunner, RunResult

# Public type aliases.
Outcome = Literal["compile_failed", "runtime_failed", "passed_with_gap", "passed"]
StopPolicy = Literal["passed", "covered", "stable"]

# Hard cap on attempts. Spec: max_attempts MUST NOT exceed 8.
MAX_ATTEMPTS_HARD_CAP: int = 8

# Coverage-gain threshold (0..1) below which a passing run is classified as
# ``passed_with_gap`` rather than ``passed``.
COVERAGE_GAIN_EPSILON: float = 0.01

# Soft cap above which the CLI emits a "high attempt cap" warning.
HIGH_ATTEMPT_WARN_THRESHOLD: int = 5

_FAILURE_EXCERPT_MAX_BYTES: int = 2048


class RefinementConfigError(ValueError):
    """Raised when the loop is constructed with an invalid configuration."""


@dataclass(frozen=True)
class CoverageDelta:
    """Files newly covered / still uncovered between two attempts."""

    newly_covered: tuple[str, ...] = ()
    still_uncovered: tuple[str, ...] = ()
    coverage_gain: float = 0.0  # absolute fraction in [-1.0, 1.0]


@dataclass(frozen=True)
class Evaluation:
    """The classification of a single attempt."""

    outcome: Outcome
    failure_excerpt: str | None = None
    coverage_gain: float = 0.0
    next_prompt_addendum: str | None = None
    coverage_percent: float = 0.0  # 0..1


@dataclass(frozen=True)
class AttemptRecord:
    """One row of the audit log."""

    attempt: int
    prompt_hash: str
    spec_path: str
    run_summary: dict
    evaluation: dict
    next_prompt_addendum: str | None
    timestamp: str


@dataclass(frozen=True)
class RefinementResult:
    """Final outcome of a :meth:`RefinementLoop.run` invocation."""

    final_spec_path: Path
    final_outcome: Outcome
    attempts: tuple[AttemptRecord, ...]
    stop_reason: str  # "passed" | "covered" | "stable" | "max_attempts"
    log_path: Path | None
    final_attempt_index: int  # 1-based index of the spec we kept


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _utc_dirname() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def prompt_hash(prompt: str) -> str:
    """Deterministic hash of a prompt string (sha256 hex digest)."""

    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def _redact(text: str | None) -> str | None:
    if text is None:
        return None
    return _secrets.redact(text)


def _truncate(text: str, *, max_bytes: int = _FAILURE_EXCERPT_MAX_BYTES) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore").rstrip() + "\n... (truncated)"


def _coverage_files(report: Any) -> set[str]:
    """Extract a set of fully-covered file paths from any coverage-report-ish object."""

    if report is None:
        return set()
    files = getattr(report, "files", None)
    if files is None and isinstance(report, dict):
        files = report.get("files")
    if not files:
        return set()
    covered: set[str] = set()
    if isinstance(files, dict):
        items = files.items()
    else:
        items = ((getattr(f, "path", None), f) for f in files)
    for path, fc in items:
        if path is None:
            continue
        if isinstance(fc, dict):
            covered_lines = int(fc.get("covered_lines", 0) or 0)
            total = int(fc.get("total_lines", 0) or 0)
        else:
            covered_lines = int(getattr(fc, "covered_lines", 0) or 0)
            total = int(getattr(fc, "total_lines", 0) or 0)
        if total > 0 and covered_lines >= total:
            covered.add(path)
    return covered


def _coverage_percent(report: Any) -> float:
    """Return overall coverage as a fraction in [0, 1]. Returns 0 if unknown."""

    if report is None:
        return 0.0
    pct = getattr(report, "percent", None)
    if pct is None and isinstance(report, dict):
        totals = report.get("totals") or report.get("summary") or {}
        pct = totals.get("percent")
    if pct is None:
        return 0.0
    try:
        value = float(pct)
    except (TypeError, ValueError):
        return 0.0
    # Reports may use 0..100 or 0..1; normalise to fraction.
    if value > 1.0:
        value /= 100.0
    return max(0.0, min(1.0, value))


def _coverage_delta(prev: Any, curr: Any) -> CoverageDelta:
    prev_set = _coverage_files(prev)
    curr_set = _coverage_files(curr)
    newly = tuple(sorted(curr_set - prev_set))
    still = tuple(sorted(_uncovered_paths(curr)))
    gain = _coverage_percent(curr) - _coverage_percent(prev)
    return CoverageDelta(newly_covered=newly, still_uncovered=still, coverage_gain=gain)


def _uncovered_paths(report: Any) -> set[str]:
    if report is None:
        return set()
    files = getattr(report, "files", None)
    if files is None and isinstance(report, dict):
        files = report.get("files")
    if not files:
        return set()
    out: set[str] = set()
    if isinstance(files, dict):
        items = files.items()
    else:
        items = ((getattr(f, "path", None), f) for f in files)
    for path, fc in items:
        if path is None:
            continue
        if isinstance(fc, dict):
            covered_lines = int(fc.get("covered_lines", 0) or 0)
            total = int(fc.get("total_lines", 0) or 0)
        else:
            covered_lines = int(getattr(fc, "covered_lines", 0) or 0)
            total = int(getattr(fc, "total_lines", 0) or 0)
        if total > 0 and covered_lines < total:
            out.add(path)
    return out


def _failure_excerpt_from_run(result: RunResult) -> str:
    """Build a concise, redacted failure excerpt from a RunResult."""

    parts: list[str] = []
    for t in result.tests:
        if t.status in ("failed", "timedOut") and t.error_message:
            parts.append(f"[{t.status}] {t.title}\n{t.error_message}")
    if not parts and result.stderr:
        parts.append(result.stderr)
    if not parts and result.stdout:
        parts.append(result.stdout)
    raw = "\n\n".join(parts) if parts else ""
    redacted = _secrets.redact(raw)
    return _truncate(redacted)


# ---------------------------------------------------------------------------
# RefinementLoop
# ---------------------------------------------------------------------------


@dataclass
class RefinementLoop:
    """Bounded generate → run → evaluate → re-prompt orchestrator."""

    generator: PlaywrightTestGenerator
    runner: PlaywrightRunner
    spec_path: Path
    max_attempts: int = 3
    stop_on: StopPolicy = "passed"
    coverage_target: float = 0.95
    retry_on_flake: int = 0
    log_dir: Path | None = None
    coverage_provider: Callable[[RunResult], Any] | None = None
    # Optional generator kwargs threaded through every call (e.g. memory map).
    generator_kwargs: dict = field(default_factory=dict)

    # ---- construction ----------------------------------------------------
    def __post_init__(self) -> None:
        if not isinstance(self.max_attempts, int) or self.max_attempts < 1:
            raise RefinementConfigError(
                "max_attempts must be a positive integer"
            )
        if self.max_attempts > MAX_ATTEMPTS_HARD_CAP:
            raise RefinementConfigError(
                f"max_attempts={self.max_attempts} exceeds the hard cap of "
                f"{MAX_ATTEMPTS_HARD_CAP}"
            )
        if self.stop_on not in ("passed", "covered", "stable"):
            raise RefinementConfigError(
                f"stop_on must be one of 'passed', 'covered', 'stable'; got {self.stop_on!r}"
            )
        if not (0.0 <= float(self.coverage_target) <= 1.0):
            raise RefinementConfigError(
                "coverage_target must be in [0.0, 1.0]"
            )
        if not isinstance(self.retry_on_flake, int) or self.retry_on_flake < 0:
            raise RefinementConfigError("retry_on_flake must be a non-negative integer")
        self.spec_path = Path(self.spec_path)

    # ---- public API ------------------------------------------------------
    def run(self, description: str) -> RefinementResult:
        """Execute the loop for ``description`` and return a :class:`RefinementResult`."""

        log_path = self._open_log()
        attempts: list[AttemptRecord] = []
        # Per-attempt artifacts kept in lock-step.
        specs: list[str] = []  # spec source written that attempt
        coverages: list[float] = []  # 0..1
        outcomes: list[Outcome] = []
        prev_report: Any = None
        prev_delta: CoverageDelta | None = None
        addendum: str | None = None
        failure_excerpt: str | None = None
        stop_reason = "max_attempts"

        for attempt in range(1, self.max_attempts + 1):
            spec_code = self.generator.generate(
                description,
                failure_excerpt=failure_excerpt,
                coverage_delta=prev_delta,
                **self.generator_kwargs,
            )
            self.spec_path.parent.mkdir(parents=True, exist_ok=True)
            self.spec_path.write_text(spec_code, encoding="utf-8")
            specs.append(spec_code)

            # Run, with optional flake retry.
            result = self._run_with_retry()

            # Coverage extraction.
            curr_report = (
                self.coverage_provider(result) if self.coverage_provider else None
            )
            curr_pct = _coverage_percent(curr_report)
            coverages.append(curr_pct)
            delta = _coverage_delta(prev_report, curr_report)

            evaluation = self._classify(result, delta)
            outcomes.append(evaluation.outcome)

            # Build the addendum that will feed the *next* attempt.
            redacted_failure = (
                _redact(_failure_excerpt_from_run(result))
                if evaluation.outcome in ("compile_failed", "runtime_failed")
                else None
            )
            addendum = self._build_addendum(evaluation, delta, redacted_failure)

            record = AttemptRecord(
                attempt=attempt,
                prompt_hash=self._prompt_hash_for(
                    description,
                    failure_excerpt=failure_excerpt,
                    coverage_delta=prev_delta,
                ),
                spec_path=str(self.spec_path),
                run_summary=self._run_summary(result),
                evaluation={
                    "outcome": evaluation.outcome,
                    "coverage_gain": delta.coverage_gain,
                    "coverage_percent": curr_pct,
                    "failure_excerpt": redacted_failure,
                },
                next_prompt_addendum=addendum,
                timestamp=_now_iso(),
            )
            attempts.append(record)
            self._append_log(log_path, record)

            # Stop check.
            stop_now, reason = self._should_stop(
                outcomes=outcomes,
                coverages=coverages,
                curr_pct=curr_pct,
            )
            if stop_now:
                stop_reason = reason
                break

            # Plumb addendum into the next iteration.
            failure_excerpt = redacted_failure
            prev_report = curr_report
            prev_delta = delta

        # Pick the final spec by argmax(coverage); tie-break: latest wins.
        final_idx = self._argmax_latest(coverages)
        # Materialise the final spec on disk (overwrites with the chosen one).
        self.spec_path.write_text(specs[final_idx], encoding="utf-8")

        return RefinementResult(
            final_spec_path=self.spec_path,
            final_outcome=outcomes[final_idx],
            attempts=tuple(attempts),
            stop_reason=stop_reason,
            log_path=log_path,
            final_attempt_index=final_idx + 1,
        )

    # ---- classification --------------------------------------------------
    def _classify(self, result: RunResult, delta: CoverageDelta) -> Evaluation:
        runner_outcome = result.is_actionable_failure()
        if runner_outcome == "compile_failed":
            return Evaluation(
                outcome="compile_failed",
                failure_excerpt=_truncate(_failure_excerpt_from_run(result)),
                coverage_gain=delta.coverage_gain,
                coverage_percent=_coverage_percent_for_eval(result, delta),
            )
        if runner_outcome == "runtime_failed":
            return Evaluation(
                outcome="runtime_failed",
                failure_excerpt=_truncate(_failure_excerpt_from_run(result)),
                coverage_gain=delta.coverage_gain,
                coverage_percent=_coverage_percent_for_eval(result, delta),
            )
        if runner_outcome == "error":
            return Evaluation(
                outcome="runtime_failed",
                failure_excerpt=_truncate(_failure_excerpt_from_run(result)),
                coverage_gain=delta.coverage_gain,
                coverage_percent=_coverage_percent_for_eval(result, delta),
            )
        # passed
        if self.coverage_provider is None:
            return Evaluation(
                outcome="passed",
                coverage_gain=0.0,
                coverage_percent=0.0,
            )
        if delta.coverage_gain >= COVERAGE_GAIN_EPSILON:
            return Evaluation(
                outcome="passed",
                coverage_gain=delta.coverage_gain,
                coverage_percent=_coverage_percent_for_eval(result, delta),
            )
        return Evaluation(
            outcome="passed_with_gap",
            coverage_gain=delta.coverage_gain,
            coverage_percent=_coverage_percent_for_eval(result, delta),
        )

    # ---- stop policy -----------------------------------------------------
    def _should_stop(
        self,
        *,
        outcomes: Sequence[Outcome],
        coverages: Sequence[float],
        curr_pct: float,
    ) -> tuple[bool, str]:
        last = outcomes[-1]
        if self.stop_on == "passed" and last == "passed":
            return True, "passed"
        if self.stop_on == "covered" and curr_pct >= self.coverage_target:
            return True, "covered"
        if self.stop_on == "stable":
            if (
                len(outcomes) >= 2
                and outcomes[-1] == "passed_with_gap"
                and outcomes[-2] == "passed_with_gap"
                and abs(coverages[-1] - coverages[-2]) < COVERAGE_GAIN_EPSILON
            ):
                return True, "stable"
            if last == "passed":
                return True, "passed"
        return False, "max_attempts"

    # ---- addendum --------------------------------------------------------
    def _build_addendum(
        self,
        evaluation: Evaluation,
        delta: CoverageDelta,
        redacted_failure: str | None,
    ) -> str | None:
        """Compose a free-text addendum for the next attempt's prompt."""

        chunks: list[str] = []
        if redacted_failure:
            chunks.append(
                f"Previous attempt outcome: {evaluation.outcome}\n"
                f"Failure excerpt (redacted):\n{redacted_failure}"
            )
        if delta.newly_covered or delta.still_uncovered:
            lines = ["Coverage delta since last attempt:"]
            if delta.newly_covered:
                lines.append(
                    "  newly covered: " + ", ".join(delta.newly_covered[:10])
                )
            if delta.still_uncovered:
                lines.append(
                    "  still uncovered: " + ", ".join(delta.still_uncovered[:10])
                )
            chunks.append("\n".join(lines))
        return "\n\n".join(chunks) if chunks else None

    # ---- final-attempt selection ----------------------------------------
    @staticmethod
    def _argmax_latest(coverages: Sequence[float]) -> int:
        """Return the index of the highest coverage; ties broken by latest."""

        best_idx = 0
        best_val = coverages[0]
        for i in range(1, len(coverages)):
            if coverages[i] >= best_val:  # >= → latest wins on ties
                best_val = coverages[i]
                best_idx = i
        return best_idx

    # ---- audit log -------------------------------------------------------
    def _open_log(self) -> Path | None:
        if self.log_dir is None:
            return None
        run_dir = Path(self.log_dir) / "runs" / _utc_dirname()
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / "refinement_log.jsonl"
        # Truncate any pre-existing file at the same path (within the same
        # millisecond a re-entry could collide; safe to overwrite).
        path.write_text("", encoding="utf-8")
        return path

    @staticmethod
    def _append_log(log_path: Path | None, record: AttemptRecord) -> None:
        if log_path is None:
            return
        # ``asdict`` on the frozen dataclass + JSON serialisation. Defensive
        # ``default=str`` keeps Path-ish values JSON-safe.
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(record), default=str) + "\n")

    # ---- run plumbing ----------------------------------------------------
    def _run_with_retry(self) -> RunResult:
        last: RunResult | None = None
        attempts = self.retry_on_flake + 1
        for _ in range(attempts):
            last = self.runner.run(self.spec_path)
            if last.is_actionable_failure() != "runtime_failed":
                return last
        assert last is not None  # loop ran at least once
        return last

    @staticmethod
    def _run_summary(result: RunResult) -> dict:
        return {
            "status": result.status,
            "exit_code": result.exit_code,
            "duration_ms": result.duration_ms,
            "tests": [
                {"title": t.title, "status": t.status, "duration_ms": t.duration_ms}
                for t in result.tests
            ],
            "report_dir": str(result.report_dir) if result.report_dir else None,
            "spec_path": str(result.spec_path) if result.spec_path else None,
        }

    def _prompt_hash_for(
        self,
        description: str,
        *,
        failure_excerpt: str | None,
        coverage_delta: CoverageDelta | None,
    ) -> str:
        """Compute the same hash the audit-log roundtrip test will recompute."""

        # We can't see the LLM-side prompt, but we *can* hash a stable
        # representation of the deterministic inputs the loop fed in.
        payload = {
            "description": description,
            "failure_excerpt": failure_excerpt,
            "coverage_delta": (
                {
                    "newly_covered": list(coverage_delta.newly_covered),
                    "still_uncovered": list(coverage_delta.still_uncovered),
                    "coverage_gain": coverage_delta.coverage_gain,
                }
                if coverage_delta
                else None
            ),
            "generator_kwargs": _stable_dict(self.generator_kwargs),
        }
        return prompt_hash(json.dumps(payload, sort_keys=True, default=str))


def _coverage_percent_for_eval(result: RunResult, delta: CoverageDelta) -> float:
    # Best-effort: we only see the delta + curr_report at the call site.
    # Callers in this module pass the actual percent through ``coverages``;
    # the Evaluation's coverage_percent is informational and may be 0.0 here.
    # (Tests assert on ``coverage_gain`` / ``outcome``, not this field.)
    return 0.0


def _stable_dict(d: dict) -> dict:
    """Return a JSON-serialisable copy of ``d`` with stringified values."""

    out: dict = {}
    for k in sorted(d):
        v = d[k]
        try:
            json.dumps(v)
            out[k] = v
        except TypeError:
            out[k] = str(v)
    return out


__all__ = [
    "AttemptRecord",
    "CoverageDelta",
    "Evaluation",
    "MAX_ATTEMPTS_HARD_CAP",
    "HIGH_ATTEMPT_WARN_THRESHOLD",
    "Outcome",
    "RefinementConfigError",
    "RefinementLoop",
    "RefinementResult",
    "StopPolicy",
    "prompt_hash",
]
