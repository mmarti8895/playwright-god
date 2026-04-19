## MODIFIED Requirements

### Requirement: The runner SHALL optionally capture frontend coverage during a run

When `PlaywrightRunner(coverage=True).run(...)` is invoked, the runner SHALL inject the bundled JS coverage fixture (or modify the resolved `playwright.config.ts` to register it), execute the run, and expose the raw per-file coverage payload on `RunResult.coverage_raw`. When `coverage=False` (default), behavior is unchanged from the `playwright-runner-integration` baseline.

#### Scenario: Coverage flag attaches the fixture and populates RunResult.coverage_raw

- **WHEN** `PlaywrightRunner(coverage=True).run(spec_path)` is called against a Chromium project
- **THEN** the run completes and `RunResult.coverage_raw` is a non-empty dict keyed by source file URL/path

#### Scenario: Default behavior is unchanged when coverage is off

- **WHEN** `PlaywrightRunner().run(spec_path)` is called (coverage defaulting to False)
- **THEN** the spec, env passthrough, exit code, and artifact directory match the `playwright-runner-integration` requirements exactly and `RunResult.coverage_raw is None`
