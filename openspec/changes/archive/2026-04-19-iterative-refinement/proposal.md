## Why

Even with a runner and coverage data, generation is still a single shot: if the spec fails to compile, the selectors are wrong, or the test passes but leaves a feature uncovered, the user is on the hook to debug, edit the prompt, and try again. A repository-aware tool should close that loop itself — running, reading the failure or the gap, re-prompting with that evidence, and converging. Without iteration, "drive a repo to 100% coverage" is a manual chore wrapped in nicer prompts.

## What Changes

- Add a `RefinementLoop` orchestrator that drives the cycle `generate → run → evaluate → re-prompt → regenerate` for a configurable number of attempts (default 3, hard cap 8).
- Add a typed `Evaluation` record per attempt: `outcome` (`compile_failed`, `runtime_failed`, `passed_with_gap`, `passed`), `failure_excerpt`, `coverage_gain`, `next_prompt_addendum`.
- Implement deterministic stop conditions: success (passed AND no gap improvement available), max attempts reached, or no measurable coverage delta across two consecutive attempts.
- Add a `playwright-god refine "<description>"` subcommand that runs the loop end-to-end and writes the final spec + a per-attempt audit log.
- Add a `--max-attempts N` and `--stop-on passed|covered|stable` flag to control loop policy.
- Persist a `refinement_log.jsonl` per run so the user (and future tools) can replay or audit the iteration.
- Treat secret redaction in failure excerpts as a hard requirement — failure logs frequently contain credentials, URLs, and tokens.

## Capabilities

### New Capabilities
- `iterative-refinement`: Orchestrating a bounded, observable generate–run–evaluate–regenerate loop with structured audit output.

### Modified Capabilities
- `test-execution`: `RunResult` gains a stable `is_actionable_failure()` helper so the loop can branch on compile vs. runtime vs. assertion failures without parsing strings.
- `coverage-driven-planning`: prompt assembly accepts a `failure_excerpt` and a `coverage_delta` produced by the loop, in addition to the existing uncovered-excerpts block.

## Impact

- **Code**: new `playwright_god/refinement.py` (RefinementLoop, Evaluation, stop conditions); small additions to `runner.py` (`is_actionable_failure`), `generator.py` (prompt addendum slots), `cli.py` (`refine` subcommand + flags).
- **Dependencies**: none new — orchestrator uses what `runner` and `coverage` already provide.
- **Tests**: new `tests/unit/test_refinement.py` (mocked runner + generator producing scripted attempt sequences); new `tests/integration/test_refinement_pipeline.py` against `sample_app`.
- **Docs**: README "Iterative refinement" section; example `refinement_log.jsonl` snippet.
- **Downstream**: feeds `spec-aware-update` (which decides whether a refined spec replaces or augments the prior spec).
