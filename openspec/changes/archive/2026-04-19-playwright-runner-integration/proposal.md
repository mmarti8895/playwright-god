## Why

Today `playwright-god generate` is a one-shot prompt → `.spec.ts` file pipeline with no feedback loop: the tool never executes the tests it produces, so it cannot tell the user (or itself) whether the generated spec actually compiles, runs, or passes against the target application. This caps the value of every downstream feature — coverage-driven planning, iterative refinement, and spec-aware updates all need a runner under them.

## What Changes

- Add a `playwright-god run` subcommand that executes a generated `.spec.ts` (or a directory of them) against a target app and captures structured results.
- Add a `--run` flag to `generate` that, after writing the spec, immediately executes it and prints/returns a result summary.
- Add a new `PlaywrightRunner` module (`playwright_god/runner.py`) that:
  - shells out to `npx playwright test --reporter=json` (or equivalent),
  - parses the JSON reporter output into a typed `RunResult` dataclass,
  - persists artifacts (HTML report, traces, videos) to a configurable directory.
- Define a `RunResult` schema (status, duration, per-test pass/fail, error messages, trace paths) consumable by future changes (`iterative-refinement`, `coverage-aware-planning`).
- Document Playwright/Node prerequisites and provide a graceful error when `npx playwright` is not on PATH.

## Capabilities

### New Capabilities
- `test-execution`: Executing generated Playwright specs against a target app and producing a structured, machine-readable result that downstream features can consume.

### Modified Capabilities
<!-- None — `generate` gains an opt-in `--run` flag, but its existing requirements are unchanged. -->

## Impact

- **Code**: new `playwright_god/runner.py`; new CLI command in `cli.py`; new `--run` flag on `generate`.
- **Dependencies**: documents (does not bundle) `node >= 18`, `npm`, `@playwright/test`. Python side adds no required deps.
- **Tests**: new `tests/unit/test_runner.py` (subprocess mocked) and `tests/integration/test_runner_pipeline.py` (uses the existing `tests/fixtures/sample_app/` as the target).
- **Docs**: README gets a "Running generated tests" section and a prerequisites note.
- **Downstream**: unblocks `coverage-aware-planning`, `iterative-refinement`, and `spec-aware-update`, all of which consume `RunResult`.
