## MODIFIED Requirements

### Requirement: A RefinementLoop SHALL orchestrate bounded generate-run-evaluate-regenerate cycles

The `playwright_god.refinement.RefinementLoop` SHALL accept a description, a generator, a runner, and a stop policy, and SHALL execute up to `max_attempts` cycles of generate → run → evaluate → re-prompt, halting as soon as a stop condition is met. The hard cap on `max_attempts` SHALL be 8. **`RefinementLoop.run(description, seed_spec: Path | None = None)` SHALL accept an optional `seed_spec` path; when provided, the seed spec's contents are included in the first attempt's prompt under a `Current spec to refine` section so the loop refines an existing test in place rather than generating from scratch.**

#### Scenario: Loop stops on first passing attempt by default

- **WHEN** `RefinementLoop(max_attempts=3, stop_on="passed").run("login flow")` is invoked and attempt 1 yields a passing run
- **THEN** no further attempts are made, the final spec is written to the configured `-o` path, and the audit log contains exactly one entry

#### Scenario: Loop honors the max-attempts cap even on failures

- **WHEN** `RefinementLoop(max_attempts=3).run(...)` is invoked and every attempt fails
- **THEN** exactly 3 attempts are executed and the final spec is the attempt with the highest coverage (ties broken by latest)

#### Scenario: max_attempts above the hard cap raises a configuration error

- **WHEN** `RefinementLoop(max_attempts=12)` is constructed
- **THEN** `RefinementConfigError` is raised whose message states the hard cap of 8

#### Scenario: Seed spec is included in the first prompt

- **WHEN** `RefinementLoop().run("login flow", seed_spec=Path("tests/login.spec.ts"))` is invoked
- **THEN** the first attempt's assembled prompt contains a `Current spec to refine` section with the seed file's contents, and the audit log entry for attempt 1 records `seed_path == "tests/login.spec.ts"`

#### Scenario: No seed leaves behavior unchanged

- **WHEN** `RefinementLoop().run("login flow")` is invoked without `seed_spec`
- **THEN** the prompt is byte-identical to the prompt produced before this change for the same inputs and `seed_path` is absent (or `null`) in the audit log
