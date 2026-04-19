## ADDED Requirements

### Requirement: A RefinementLoop SHALL orchestrate bounded generate-run-evaluate-regenerate cycles

The `playwright_god.refinement.RefinementLoop` SHALL accept a description, a generator, a runner, and a stop policy, and SHALL execute up to `max_attempts` cycles of generate → run → evaluate → re-prompt, halting as soon as a stop condition is met. The hard cap on `max_attempts` SHALL be 8.

#### Scenario: Loop stops on first passing attempt by default

- **WHEN** `RefinementLoop(max_attempts=3, stop_on="passed").run("login flow")` is invoked and attempt 1 yields a passing run
- **THEN** no further attempts are made, the final spec is written to the configured `-o` path, and the audit log contains exactly one entry

#### Scenario: Loop honors the max-attempts cap even on failures

- **WHEN** `RefinementLoop(max_attempts=3).run(...)` is invoked and every attempt fails
- **THEN** exactly 3 attempts are executed and the final spec is the attempt with the highest coverage (ties broken by latest)

#### Scenario: max_attempts above the hard cap raises a configuration error

- **WHEN** `RefinementLoop(max_attempts=12)` is constructed
- **THEN** `RefinementConfigError` is raised whose message states the hard cap of 8

### Requirement: Each attempt SHALL produce a typed Evaluation with one of four outcomes

Each attempt SHALL produce an `Evaluation` whose `outcome` is exactly one of `compile_failed`, `runtime_failed`, `passed_with_gap`, or `passed`, derived from the `RunResult` and (if present) the coverage delta.

#### Scenario: Compile failure is classified as compile_failed

- **WHEN** the underlying `RunResult.is_actionable_failure()` returns `"compile_failed"`
- **THEN** `Evaluation.outcome == "compile_failed"` and `Evaluation.failure_excerpt` contains the compiler error truncated to ≤ 2KB

#### Scenario: Passing run with no coverage gain is classified as passed_with_gap

- **WHEN** the run passes but the coverage delta versus the prior attempt is `< 1%`
- **THEN** `Evaluation.outcome == "passed_with_gap"` and `Evaluation.next_prompt_addendum` contains uncovered excerpts ranked by feature membership

#### Scenario: Passing run with meaningful coverage gain is classified as passed

- **WHEN** the run passes AND coverage delta `>= 1%` (or coverage tracking is disabled)
- **THEN** `Evaluation.outcome == "passed"` and the loop stop policy is consulted

### Requirement: Stop conditions SHALL be explicit and orthogonal

The loop SHALL support stop policies `passed` (default), `covered`, and `stable`, in addition to the always-applicable `max_attempts` hard limit.

#### Scenario: `covered` stops only at the target coverage

- **WHEN** `RefinementLoop(stop_on="covered", coverage_target=0.95).run(...)` is invoked and attempt 2 passes at 80% feature coverage
- **THEN** the loop continues to attempt 3 (subject to the cap)

#### Scenario: `stable` stops on a coverage plateau

- **WHEN** stop policy is `stable` and attempts 2 and 3 both pass with `passed_with_gap` outcome and zero coverage delta between them
- **THEN** the loop halts after attempt 3 and the audit log records `stop_reason == "stable"`

### Requirement: A refinement_log.jsonl SHALL persist a per-attempt audit trail

A `refinement_log.jsonl` SHALL be written under `<persist-dir>/runs/<timestamp>/` containing exactly one JSON object per attempt with the fields `attempt`, `prompt_hash`, `spec_path`, `run_summary`, `evaluation`, and `next_prompt_addendum`. The file SHALL be append-only within a run.

#### Scenario: Each attempt appends one JSON line

- **WHEN** a 3-attempt run completes
- **THEN** `refinement_log.jsonl` contains exactly 3 lines, each a valid JSON object, in attempt order

#### Scenario: Audit log is replayable

- **WHEN** an external consumer reads `refinement_log.jsonl` and reconstructs the prompts using `prompt_hash`
- **THEN** the reconstructed prompts match what was sent (verifiable in tests via the same hash function)

### Requirement: Failure excerpts MUST be redacted before being used as prompt context

Before any `failure_excerpt` or `next_prompt_addendum` derived from runtime output is included in a subsequent prompt, it SHALL pass through the centralized `playwright_god._secrets.redact` function and SHALL NOT contain any of the patterns matched by `_SECRET_PATTERNS`.

#### Scenario: Bearer tokens in failure logs are redacted

- **WHEN** a runtime failure log contains `Authorization: Bearer sk-abcdef0123456789`
- **THEN** the corresponding `next_prompt_addendum` contains `Authorization: Bearer [REDACTED]` and the original token does not appear anywhere in the audit log

#### Scenario: Known API key shapes are redacted

- **WHEN** a failure log contains `OPENAI_API_KEY=sk-proj-XYZ...` (any provider key shape recognized by `_SECRET_PATTERNS`)
- **THEN** the value is replaced with `[REDACTED]` in both the next prompt addendum and the audit log

### Requirement: A `refine` CLI subcommand SHALL drive the loop end-to-end

The CLI SHALL provide `playwright-god refine "<description>" [-o PATH] [--max-attempts N] [--stop-on passed|covered|stable] [--coverage-target FLOAT] [--retry-on-flake N]` that constructs and runs a `RefinementLoop` with sensible defaults.

#### Scenario: Default invocation runs at most 3 attempts and stops on first pass

- **WHEN** `playwright-god refine "login flow" -o tests/login.spec.ts` is invoked
- **THEN** at most 3 attempts execute, the loop stops at the first `passed` outcome, and the final spec is written to `tests/login.spec.ts`

#### Scenario: --max-attempts greater than 5 emits a warning

- **WHEN** `playwright-god refine ... --max-attempts 7` is invoked
- **THEN** a warning containing `"high attempt cap"` is printed to stderr before the loop starts, and the loop honors the requested cap up to the hard limit of 8

#### Scenario: Loop exit code reflects the final outcome

- **WHEN** the final attempt's outcome is `passed`
- **THEN** the CLI exits 0; otherwise it exits non-zero
