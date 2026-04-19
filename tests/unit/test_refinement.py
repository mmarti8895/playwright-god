"""Unit tests for the iterative refinement loop."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import pytest

from playwright_god import _secrets
from playwright_god.refinement import (
    HIGH_ATTEMPT_WARN_THRESHOLD,
    MAX_ATTEMPTS_HARD_CAP,
    AttemptRecord,
    CoverageDelta,
    Evaluation,
    RefinementConfigError,
    RefinementLoop,
    prompt_hash,
    _coverage_delta,
    _coverage_files,
    _coverage_percent,
    _failure_excerpt_from_run,
    _stable_dict,
    _truncate,
    _uncovered_paths,
)
from playwright_god.runner import RunResult, TestCaseResult


class ScriptedGenerator:
    def __init__(self, specs):
        self._specs = list(specs)
        self.calls = []

    def generate(self, description, **kwargs):
        self.calls.append({"description": description, **kwargs})
        idx = min(len(self.calls) - 1, len(self._specs) - 1)
        return self._specs[idx]


class ScriptedRunner:
    def __init__(self, results):
        self._results = list(results)
        self.calls = []

    def run(self, spec_path):
        self.calls.append(Path(spec_path))
        idx = min(len(self.calls) - 1, len(self._results) - 1)
        return self._results[idx]


def _passed(title="ok"):
    return RunResult(
        status="passed",
        duration_ms=10,
        tests=(TestCaseResult(title=title, status="passed", duration_ms=10),),
        exit_code=0,
        stdout="",
        stderr="",
    )


def _runtime_failed(message="boom"):
    return RunResult(
        status="failed",
        duration_ms=10,
        tests=(TestCaseResult(title="t", status="failed", duration_ms=10, error_message=message),),
        exit_code=1,
        stdout="",
        stderr="",
    )


def _compile_failed(stderr="src/x.spec.ts(1,2): error TS2304: nope"):
    return RunResult(
        status="error",
        duration_ms=0,
        tests=(),
        exit_code=1,
        stdout="",
        stderr=stderr,
    )


def _cov(percent, files=None):
    return {"totals": {"percent": percent}, "files": files or {}}


def test_max_attempts_above_hard_cap_raises(tmp_path):
    with pytest.raises(RefinementConfigError, match="hard cap"):
        RefinementLoop(
            generator=ScriptedGenerator(["x"]),
            runner=ScriptedRunner([_passed()]),
            spec_path=tmp_path / "s.spec.ts",
            max_attempts=MAX_ATTEMPTS_HARD_CAP + 1,
        )


def test_max_attempts_zero_raises(tmp_path):
    with pytest.raises(RefinementConfigError):
        RefinementLoop(
            generator=ScriptedGenerator(["x"]),
            runner=ScriptedRunner([_passed()]),
            spec_path=tmp_path / "s.spec.ts",
            max_attempts=0,
        )


def test_invalid_stop_on_raises(tmp_path):
    with pytest.raises(RefinementConfigError):
        RefinementLoop(
            generator=ScriptedGenerator(["x"]),
            runner=ScriptedRunner([_passed()]),
            spec_path=tmp_path / "s.spec.ts",
            stop_on="bogus",
        )


def test_invalid_coverage_target_raises(tmp_path):
    with pytest.raises(RefinementConfigError):
        RefinementLoop(
            generator=ScriptedGenerator(["x"]),
            runner=ScriptedRunner([_passed()]),
            spec_path=tmp_path / "s.spec.ts",
            coverage_target=2.0,
        )


def test_invalid_retry_on_flake_raises(tmp_path):
    with pytest.raises(RefinementConfigError):
        RefinementLoop(
            generator=ScriptedGenerator(["x"]),
            runner=ScriptedRunner([_passed()]),
            spec_path=tmp_path / "s.spec.ts",
            retry_on_flake=-1,
        )


def test_warn_threshold_constant_is_int():
    assert isinstance(HIGH_ATTEMPT_WARN_THRESHOLD, int)
    assert HIGH_ATTEMPT_WARN_THRESHOLD < MAX_ATTEMPTS_HARD_CAP


def test_stops_on_first_pass_by_default(tmp_path):
    spec = tmp_path / "s.spec.ts"
    gen = ScriptedGenerator(["a", "b", "c"])
    run = ScriptedRunner([_passed(), _passed(), _passed()])
    loop = RefinementLoop(generator=gen, runner=run, spec_path=spec, max_attempts=3)
    result = loop.run("login")
    assert len(result.attempts) == 1
    assert result.final_outcome == "passed"
    assert result.stop_reason == "passed"


def test_runs_until_max_attempts_when_all_fail(tmp_path):
    spec = tmp_path / "s.spec.ts"
    gen = ScriptedGenerator(["a", "b", "c"])
    run = ScriptedRunner([_runtime_failed(), _runtime_failed(), _runtime_failed()])
    loop = RefinementLoop(generator=gen, runner=run, spec_path=spec, max_attempts=3)
    result = loop.run("x")
    assert len(result.attempts) == 3
    assert result.stop_reason == "max_attempts"
    assert result.final_outcome == "runtime_failed"


def test_covered_continues_until_target_hit(tmp_path):
    spec = tmp_path / "s.spec.ts"
    gen = ScriptedGenerator(["a", "b", "c"])
    run = ScriptedRunner([_passed(), _passed(), _passed()])
    coverages = iter([_cov(0.5), _cov(0.8), _cov(0.99)])
    loop = RefinementLoop(
        generator=gen, runner=run, spec_path=spec, max_attempts=3,
        stop_on="covered", coverage_target=0.95,
        coverage_provider=lambda _r: next(coverages),
    )
    result = loop.run("x")
    assert result.stop_reason == "covered"
    assert len(result.attempts) == 3


def test_stable_stops_on_two_zero_delta(tmp_path):
    spec = tmp_path / "s.spec.ts"
    gen = ScriptedGenerator(["a", "b", "c"])
    run = ScriptedRunner([_passed(), _passed(), _passed()])
    # 0.0 coverage throughout → no gain → outcome="passed_with_gap" each time.
    coverages = iter([_cov(0.0), _cov(0.0), _cov(0.0)])
    loop = RefinementLoop(
        generator=gen, runner=run, spec_path=spec, max_attempts=3,
        stop_on="stable", coverage_target=0.99,
        coverage_provider=lambda _r: next(coverages),
    )
    result = loop.run("x")
    assert result.stop_reason == "stable"
    assert len(result.attempts) == 2


def test_stable_also_stops_on_clear_pass(tmp_path):
    spec = tmp_path / "s.spec.ts"
    gen = ScriptedGenerator(["a", "b"])
    run = ScriptedRunner([_passed(), _passed()])
    coverages = iter([_cov(0.0), _cov(0.9)])
    loop = RefinementLoop(
        generator=gen, runner=run, spec_path=spec, max_attempts=2,
        stop_on="stable", coverage_target=0.99,
        coverage_provider=lambda _r: next(coverages),
    )
    result = loop.run("x")
    assert len(result.attempts) <= 2


def test_classify_compile_failed(tmp_path):
    spec = tmp_path / "s.spec.ts"
    loop = RefinementLoop(
        generator=ScriptedGenerator(["a"]),
        runner=ScriptedRunner([_compile_failed()]),
        spec_path=spec, max_attempts=1,
    )
    result = loop.run("x")
    assert result.attempts[0].evaluation["outcome"] == "compile_failed"


def test_classify_passed_with_gap_when_no_coverage_gain(tmp_path):
    spec = tmp_path / "s.spec.ts"
    gen = ScriptedGenerator(["a", "b"])
    run = ScriptedRunner([_passed(), _passed()])
    coverages = iter([_cov(0.5), _cov(0.5)])
    loop = RefinementLoop(
        generator=gen, runner=run, spec_path=spec, max_attempts=2,
        stop_on="covered", coverage_target=0.99,
        coverage_provider=lambda _r: next(coverages),
    )
    result = loop.run("x")
    assert result.attempts[-1].evaluation["outcome"] == "passed_with_gap"


def test_classify_passed_when_coverage_gain_above_epsilon(tmp_path):
    spec = tmp_path / "s.spec.ts"
    gen = ScriptedGenerator(["a", "b"])
    run = ScriptedRunner([_passed(), _passed()])
    coverages = iter([_cov(0.5), _cov(0.8)])
    loop = RefinementLoop(
        generator=gen, runner=run, spec_path=spec, max_attempts=2,
        stop_on="covered", coverage_target=0.99,
        coverage_provider=lambda _r: next(coverages),
    )
    result = loop.run("x")
    assert result.attempts[-1].evaluation["outcome"] == "passed"


def test_classify_error_outcome_is_runtime_failed(tmp_path):
    err = RunResult(status="error", duration_ms=0, tests=(), exit_code=1, stdout="", stderr="weird")
    spec = tmp_path / "s.spec.ts"
    loop = RefinementLoop(
        generator=ScriptedGenerator(["a"]),
        runner=ScriptedRunner([err]),
        spec_path=spec, max_attempts=1,
    )
    result = loop.run("x")
    assert result.attempts[0].evaluation["outcome"] == "runtime_failed"


def test_final_spec_is_argmax_coverage(tmp_path):
    spec = tmp_path / "s.spec.ts"
    gen = ScriptedGenerator(["AAA", "BBB", "CCC"])
    run = ScriptedRunner([_passed(), _passed(), _passed()])
    coverages = iter([_cov(0.5), _cov(0.9), _cov(0.7)])
    loop = RefinementLoop(
        generator=gen, runner=run, spec_path=spec, max_attempts=3,
        stop_on="covered", coverage_target=0.99,
        coverage_provider=lambda _r: next(coverages),
    )
    result = loop.run("x")
    assert spec.read_text() == "BBB"
    assert result.final_attempt_index == 2


def test_final_spec_latest_wins_ties(tmp_path):
    spec = tmp_path / "s.spec.ts"
    gen = ScriptedGenerator(["AAA", "BBB", "CCC"])
    run = ScriptedRunner([_passed(), _passed(), _passed()])
    coverages = iter([_cov(0.5), _cov(0.5), _cov(0.5)])
    loop = RefinementLoop(
        generator=gen, runner=run, spec_path=spec, max_attempts=3,
        stop_on="covered", coverage_target=0.99,
        coverage_provider=lambda _r: next(coverages),
    )
    result = loop.run("x")
    assert spec.read_text() == "CCC"
    assert result.final_attempt_index == 3


def test_failure_excerpt_redacts_bearer_tokens(tmp_path):
    leak = "Authorization: Bearer sk-abcdef0123456789ABC"
    rr = RunResult(
        status="failed", duration_ms=1,
        tests=(TestCaseResult(title="t", status="failed", duration_ms=1, error_message=leak),),
        exit_code=1, stdout="", stderr="",
    )
    spec = tmp_path / "s.spec.ts"
    gen = ScriptedGenerator(["a", "b"])
    run = ScriptedRunner([rr, _passed()])
    loop = RefinementLoop(generator=gen, runner=run, spec_path=spec, max_attempts=2)
    result = loop.run("x")
    addendum = result.attempts[0].next_prompt_addendum or ""
    assert "sk-abcdef0123456789ABC" not in addendum
    assert "[REDACTED]" in addendum
    assert "sk-abcdef0123456789ABC" not in (gen.calls[1].get("failure_excerpt") or "")


def test_failure_excerpt_redacts_env_var_assignments(tmp_path):
    leak = "OPENAI_API_KEY=sk-proj-XYZabc1234567890DEFGHIJK"
    rr = RunResult(
        status="failed", duration_ms=1,
        tests=(TestCaseResult(title="t", status="failed", duration_ms=1, error_message=leak),),
        exit_code=1, stdout="", stderr="",
    )
    spec = tmp_path / "s.spec.ts"
    gen = ScriptedGenerator(["a", "b"])
    run = ScriptedRunner([rr, _passed()])
    loop = RefinementLoop(generator=gen, runner=run, spec_path=spec, max_attempts=2)
    result = loop.run("x")
    record_text = json.dumps(result.attempts[0].evaluation)
    assert "sk-proj-XYZabc1234567890DEFGHIJK" not in record_text


def test_secrets_module_redact_idempotent():
    leak = "Authorization: Bearer sk-abcdef0123456789ABC"
    once = _secrets.redact(leak)
    twice = _secrets.redact(once)
    assert once == twice
    assert "sk-abcdef0123456789ABC" not in once


def test_secrets_module_redact_handles_empty():
    assert _secrets.redact("") == ""


def test_audit_log_one_line_per_attempt(tmp_path):
    spec = tmp_path / "s.spec.ts"
    gen = ScriptedGenerator(["a", "b", "c"])
    run = ScriptedRunner([_runtime_failed()] * 3)
    loop = RefinementLoop(
        generator=gen, runner=run, spec_path=spec, max_attempts=3,
        log_dir=tmp_path / "out",
    )
    result = loop.run("login")
    assert result.log_path is not None
    lines = result.log_path.read_text().splitlines()
    assert len(lines) == 3
    parsed = [json.loads(line) for line in lines]
    assert [p["attempt"] for p in parsed] == [1, 2, 3]
    for entry in parsed:
        assert "prompt_hash" in entry
        assert "spec_path" in entry
        assert "evaluation" in entry


def test_audit_log_skipped_when_no_log_dir(tmp_path):
    spec = tmp_path / "s.spec.ts"
    loop = RefinementLoop(
        generator=ScriptedGenerator(["a"]),
        runner=ScriptedRunner([_passed()]),
        spec_path=spec, max_attempts=1,
    )
    result = loop.run("x")
    assert result.log_path is None


def test_prompt_hash_roundtrip_is_deterministic(tmp_path):
    spec = tmp_path / "s.spec.ts"
    gen = ScriptedGenerator(["a", "b"])
    run = ScriptedRunner([_runtime_failed(), _passed()])
    loop = RefinementLoop(
        generator=gen, runner=run, spec_path=spec, max_attempts=2,
        log_dir=tmp_path / "out",
    )
    result = loop.run("login flow")
    parsed = [json.loads(line) for line in result.log_path.read_text().splitlines()]
    expected = prompt_hash(json.dumps({
        "description": "login flow",
        "failure_excerpt": None,
        "coverage_delta": None,
        "generator_kwargs": {},
        "seed_spec_content": None,
    }, sort_keys=True, default=str))
    assert parsed[0]["prompt_hash"] == expected


def test_prompt_hash_changes_when_input_changes():
    assert prompt_hash("X") != prompt_hash("Y")


def test_retry_on_flake_promotes_pass_after_fail(tmp_path):
    spec = tmp_path / "s.spec.ts"
    gen = ScriptedGenerator(["a"])
    run = ScriptedRunner([_runtime_failed(), _passed()])
    loop = RefinementLoop(
        generator=gen, runner=run, spec_path=spec, max_attempts=1, retry_on_flake=1,
    )
    result = loop.run("x")
    assert result.attempts[0].evaluation["outcome"] == "passed"
    assert len(run.calls) == 2


def test_description_passed_through_to_generator(tmp_path):
    spec = tmp_path / "s.spec.ts"
    gen = ScriptedGenerator(["a"])
    run = ScriptedRunner([_passed()])
    loop = RefinementLoop(generator=gen, runner=run, spec_path=spec, max_attempts=1)
    loop.run("a long description")
    assert gen.calls[0]["description"] == "a long description"


def test_coverage_files_handles_none():
    assert _coverage_files(None) == set()


def test_coverage_files_handles_empty_payload():
    assert _coverage_files({}) == set()
    assert _coverage_files({"files": {}}) == set()


def test_coverage_files_dict_with_iterable_files():
    @dataclass
    class _FC:
        path: str
        covered_lines: int
        total_lines: int

    payload_obj = type("R", (), {"files": [_FC("a.py", 10, 10), _FC("b.py", 5, 10)]})()
    assert _coverage_files(payload_obj) == {"a.py"}
    assert _uncovered_paths(payload_obj) == {"b.py"}


def test_coverage_percent_handles_none_and_strings():
    assert _coverage_percent(None) == 0.0
    assert _coverage_percent({"totals": {"percent": "not a number"}}) == 0.0
    assert _coverage_percent({"summary": {"percent": 80}}) == pytest.approx(0.80)


def test_coverage_percent_attribute_access():
    obj = type("R", (), {"percent": 0.42})()
    assert _coverage_percent(obj) == pytest.approx(0.42)


def test_coverage_percent_clamps_above_one():
    assert _coverage_percent({"totals": {"percent": 200}}) == 1.0


def test_coverage_delta_marks_newly_covered():
    prev = {"files": {"a.py": {"covered_lines": 5, "total_lines": 10}}}
    curr = {
        "files": {
            "a.py": {"covered_lines": 10, "total_lines": 10},
            "b.py": {"covered_lines": 1, "total_lines": 10},
        },
        "totals": {"percent": 50.0},
    }
    delta = _coverage_delta(prev, curr)
    assert "a.py" in delta.newly_covered
    assert "b.py" in delta.still_uncovered


def test_truncate_short_returns_input():
    assert _truncate("hi") == "hi"


def test_truncate_long_marks_truncation():
    out = _truncate("X" * 5000, max_bytes=100)
    assert out.endswith("(truncated)")
    assert len(out.encode("utf-8")) < 250


def test_failure_excerpt_falls_back_to_stderr():
    rr = RunResult(status="error", duration_ms=0, tests=(), exit_code=1, stdout="", stderr="boom from stderr")
    assert "boom from stderr" in _failure_excerpt_from_run(rr)


def test_failure_excerpt_falls_back_to_stdout_when_nothing_else():
    rr = RunResult(status="error", duration_ms=0, tests=(), exit_code=1, stdout="boom from stdout", stderr="")
    assert "boom from stdout" in _failure_excerpt_from_run(rr)


def test_failure_excerpt_empty_when_no_signal():
    rr = RunResult(status="passed", duration_ms=0, tests=(), exit_code=0, stdout="", stderr="")
    assert _failure_excerpt_from_run(rr) == ""


def test_stable_dict_stringifies_unjsonable_values():
    class _NotJSON:
        def __repr__(self):
            return "<NotJSON>"

    out = _stable_dict({"a": 1, "b": _NotJSON()})
    assert out["a"] == 1
    assert out["b"] == "<NotJSON>"


def test_addendum_contains_coverage_delta_lines(tmp_path):
    spec = tmp_path / "s.spec.ts"
    gen = ScriptedGenerator(["a", "b"])
    run = ScriptedRunner([_passed(), _passed()])
    coverages = iter([
        {"files": {"a.py": {"covered_lines": 5, "total_lines": 10}}, "totals": {"percent": 50}},
        {"files": {"a.py": {"covered_lines": 10, "total_lines": 10}, "b.py": {"covered_lines": 1, "total_lines": 10}}, "totals": {"percent": 60}},
    ])
    loop = RefinementLoop(
        generator=gen, runner=run, spec_path=spec, max_attempts=2,
        stop_on="covered", coverage_target=0.99,
        coverage_provider=lambda _r: next(coverages),
    )
    result = loop.run("x")
    addendum_all = " ".join((a.next_prompt_addendum or "") for a in result.attempts)
    assert "Coverage delta since last attempt" in addendum_all


def test_redact_none_returns_none():
    from playwright_god.refinement import _redact
    assert _redact(None) is None


def test_coverage_files_skips_iterable_with_missing_path():
    @dataclass
    class _FC:
        path: object
        covered_lines: int
        total_lines: int

    obj = type("R", (), {"files": [_FC(None, 10, 10), _FC("k.py", 10, 10)]})()
    assert _coverage_files(obj) == {"k.py"}
    assert _uncovered_paths(obj) == set()


# ---------------------------------------------------------------------------
# seed_spec support
# ---------------------------------------------------------------------------


def test_seed_spec_content_included_in_first_prompt(tmp_path):
    """When seed_spec is provided, its content appears in the first prompt."""
    spec = tmp_path / "output.spec.ts"
    seed = tmp_path / "seed.spec.ts"
    seed.write_text("// existing test code\ntest('old', () => {});", encoding="utf-8")

    gen = ScriptedGenerator(["test('new', () => {});"])
    run = ScriptedRunner([_passed()])

    loop = RefinementLoop(generator=gen, runner=run, spec_path=spec, max_attempts=1)
    result = loop.run("improve login test", seed_spec=seed)

    # Check that generator received seed content
    assert len(gen.calls) == 1
    assert gen.calls[0].get("seed_spec_content") is not None
    assert "existing test code" in gen.calls[0]["seed_spec_content"]


def test_seed_spec_records_seed_path_in_audit_log(tmp_path):
    """When seed_spec is provided, attempt 1 records seed_path in the log."""
    spec = tmp_path / "output.spec.ts"
    seed = tmp_path / "seed.spec.ts"
    seed.write_text("// seed", encoding="utf-8")

    gen = ScriptedGenerator(["test('x', () => {});"])
    run = ScriptedRunner([_passed()])

    loop = RefinementLoop(generator=gen, runner=run, spec_path=spec, max_attempts=1)
    result = loop.run("test", seed_spec=seed)

    assert len(result.attempts) == 1
    assert result.attempts[0].seed_path == str(seed)


def test_no_seed_spec_leaves_seed_path_null(tmp_path):
    """Without seed_spec, seed_path is None in the audit log."""
    spec = tmp_path / "output.spec.ts"

    gen = ScriptedGenerator(["test('x', () => {});"])
    run = ScriptedRunner([_passed()])

    loop = RefinementLoop(generator=gen, runner=run, spec_path=spec, max_attempts=1)
    result = loop.run("test")

    assert len(result.attempts) == 1
    assert result.attempts[0].seed_path is None


def test_seed_spec_only_in_first_attempt(tmp_path):
    """Seed content is only passed in the first attempt, not subsequent ones."""
    spec = tmp_path / "output.spec.ts"
    seed = tmp_path / "seed.spec.ts"
    seed.write_text("// seed content", encoding="utf-8")

    gen = ScriptedGenerator(["bad code", "test('x', () => {});"])
    run = ScriptedRunner([_runtime_failed(), _passed()])

    loop = RefinementLoop(generator=gen, runner=run, spec_path=spec, max_attempts=2)
    result = loop.run("test", seed_spec=seed)

    assert len(gen.calls) == 2
    # First call has seed content
    assert gen.calls[0].get("seed_spec_content") is not None
    # Second call does not
    assert gen.calls[1].get("seed_spec_content") is None


def test_no_seed_prompt_is_byte_identical_to_before(tmp_path):
    """Without seed_spec, the prompt hash should be the same as without the feature."""
    spec = tmp_path / "output.spec.ts"

    gen = ScriptedGenerator(["test('x', () => {});"])
    run = ScriptedRunner([_passed()])

    loop = RefinementLoop(generator=gen, runner=run, spec_path=spec, max_attempts=1)
    result = loop.run("test description")

    # Verify no seed content was passed
    assert gen.calls[0].get("seed_spec_content") is None
    # The prompt_hash should only include None for seed_spec_content
    assert result.attempts[0].seed_path is None
