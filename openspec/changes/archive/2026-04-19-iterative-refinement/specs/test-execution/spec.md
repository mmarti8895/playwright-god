## MODIFIED Requirements

### Requirement: RunResult SHALL expose a stable is_actionable_failure() classifier

`RunResult` SHALL provide `is_actionable_failure() -> Literal["compile_failed", "runtime_failed", "passed", "error"]` derived deterministically from `exit_code`, the JSON reporter content, and `stderr` heuristics, so callers (refinement loop, spec-aware-update) need not parse strings themselves.

#### Scenario: TypeScript compile error returns compile_failed

- **WHEN** the run's stderr contains a TypeScript compiler error pattern (e.g. `error TS\d+:`) and zero tests were reported as executed
- **THEN** `is_actionable_failure()` returns `"compile_failed"`

#### Scenario: Test assertion failure returns runtime_failed

- **WHEN** the JSON reporter records at least one test with status `"failed"`
- **THEN** `is_actionable_failure()` returns `"runtime_failed"`

#### Scenario: Successful run returns passed

- **WHEN** `exit_code == 0` and every reported test status is `"passed"` (or skipped)
- **THEN** `is_actionable_failure()` returns `"passed"`

#### Scenario: Setup/runner errors return error

- **WHEN** the run never started a test (e.g. `RunnerSetupError` was raised, or the reporter file is missing)
- **THEN** `is_actionable_failure()` returns `"error"`
