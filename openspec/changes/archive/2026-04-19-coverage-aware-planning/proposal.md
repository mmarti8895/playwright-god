## Why

Even with a runner in place, `playwright-god` has no concept of what code in the *target* repository is actually exercised by its generated tests. Without a coverage signal, "drive the repo to 100% test coverage" is a slogan, not a workflow — the tool can't prioritize, can't measure progress, and can't tell the user which features still need tests. We need a coverage feedback channel that turns subjective "we wrote some tests" into objective "X% of routes / Y% of components / Z% of backend lines are still uncovered."

## What Changes

- Add a `CoverageCollector` that wraps a `PlaywrightRunner` (from `playwright-runner-integration`) and instruments the run to capture coverage data from two sources:
  - **Frontend JS coverage** via Playwright's built-in `page.coverage.startJSCoverage()` injected through a generated fixture, post-processed into per-file line coverage.
  - **Backend coverage** via an opt-in side-channel: when the user sets `--backend-coverage cmd "pytest --cov ..."` or `"coverage erase && coverage run -m ..."`, the collector starts/stops the backend coverage process around the Playwright run.
- Add a typed `CoverageReport` (per-file / per-line, with `total_lines`, `covered_lines`, `percent`) and a `MergedCoverageReport` that joins frontend + backend.
- Extend `MemoryMap` (schema bump to `2.1`) with an optional `coverage` block: per-file coverage, per-feature aggregated coverage, and a `gaps` list (uncovered files/lines tagged to inferred features).
- Extend the `plan` command and `PlaywrightTestGenerator` prompt to:
  - sort feature areas by *uncovered* size (highest gap first),
  - pass uncovered file/line excerpts as RAG context so generated specs target gaps,
  - emit a "Coverage delta" section in the Markdown plan.
- Add a `playwright-god coverage report` subcommand that prints the merged report (text/JSON/HTML) without re-running.

## Capabilities

### New Capabilities
- `coverage-collection`: Capturing JS and (optionally) backend coverage during a Playwright run and persisting a structured per-file report.
- `coverage-driven-planning`: Using the coverage report to prioritize feature areas with the largest gaps when generating plans and specs.

### Modified Capabilities
- `test-execution`: `PlaywrightRunner` gains an opt-in `coverage=True` mode that injects the JS-coverage fixture and exposes the resulting raw data on `RunResult.coverage_raw`.

## Impact

- **Code**: new `playwright_god/coverage.py` (CoverageCollector, CoverageReport, MergedCoverageReport); modifications to `runner.py`, `memory_map.py` (schema 2.1), `generator.py` (prompt assembly), `cli.py` (`coverage report` + new flags on `generate`/`plan`).
- **Dependencies**: new optional extra `[coverage]` pulling `coverage>=7` (Python backend) and a small JS helper bundled in `playwright_god/_assets/coverage_fixture.ts` for frontend.
- **Tests**: new `tests/unit/test_coverage.py`, fixture `tests/fixtures/coverage_sample.json`, integration test piggybacking on `sample_app`.
- **Docs**: README "Coverage-driven workflow" section; `MemoryMap` schema doc bumped to `2.1` with a migration note.
- **Downstream**: feeds `iterative-refinement` (gap-as-prompt) and is consumed by `spec-aware-update` (which tests need re-running after a coverage-affecting change).
