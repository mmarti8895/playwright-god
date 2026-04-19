## ADDED Requirements

### Requirement: A PlaywrightRunner SHALL execute generated specs and return a structured result

The `playwright_god.runner.PlaywrightRunner` class SHALL accept a path to a `.spec.ts` file (or a directory containing them) and return a `RunResult` dataclass containing overall status, duration, per-test outcomes, raw stdout/stderr, the subprocess exit code, and the path to the artifact directory.

#### Scenario: Successful run produces a passed RunResult

- **WHEN** `PlaywrightRunner().run(spec_path)` is called against a spec whose Playwright execution exits with code `0`
- **THEN** the returned `RunResult.status` is `"passed"`, `exit_code` is `0`, and every entry in `tests` has `status == "passed"`

#### Scenario: Failing run produces a failed RunResult with per-test details

- **WHEN** `PlaywrightRunner().run(spec_path)` is called against a spec whose Playwright execution exits with a non-zero code and the JSON reporter reports at least one failed test
- **THEN** the returned `RunResult.status` is `"failed"`, `exit_code` matches the subprocess exit code, and the failing `TestCaseResult` includes a non-empty `error_message`

#### Scenario: Run preserves artifacts on disk

- **WHEN** `PlaywrightRunner(artifact_dir=Path("/tmp/pg-run"))` executes a spec
- **THEN** the Playwright HTML report and any traces/videos are written under `/tmp/pg-run/<timestamp>/` and `RunResult.report_dir` points at that directory

### Requirement: The runner SHALL fail fast with actionable errors when prerequisites are missing

`PlaywrightRunner` SHALL detect missing Node/npm/`@playwright/test` prerequisites before invoking the subprocess and SHALL raise `RunnerSetupError` whose message names the missing tool and the remediation command.

#### Scenario: npx is not on PATH

- **WHEN** `PlaywrightRunner().run(spec_path)` is invoked in an environment where `shutil.which("npx")` returns `None`
- **THEN** `RunnerSetupError` is raised whose message contains both `"npx"` and instructions to install Node 18+

#### Scenario: @playwright/test is not installed in the target directory

- **WHEN** the resolved working directory has a `package.json` that does not list `@playwright/test` as a (dev)dependency
- **THEN** `RunnerSetupError` is raised whose message contains `"@playwright/test"` and the install command `npm i -D @playwright/test`

#### Scenario: No package.json can be located

- **WHEN** the spec path's ancestor directories contain no `package.json` and no `--target-dir` was provided
- **THEN** `RunnerSetupError` is raised whose message contains `"package.json"` and instructs the user to pass `--target-dir`

### Requirement: The CLI SHALL expose `run` as a subcommand and `--run` as a generate flag

The `playwright-god` CLI SHALL gain a `run` subcommand and a `--run` flag on `generate` that both delegate to `PlaywrightRunner`.

#### Scenario: `playwright-god run <spec>` executes the spec

- **WHEN** the user invokes `playwright-god run tests/example.spec.ts`
- **THEN** `PlaywrightRunner.run` is called with that path and the resulting `RunResult` summary is printed to stdout, with the process exit code matching `RunResult.exit_code`

#### Scenario: `playwright-god generate ... --run` chains generation and execution

- **WHEN** the user invokes `playwright-god generate "login flow" -o tests/login.spec.ts --run`
- **THEN** the spec is written to `tests/login.spec.ts` and immediately executed, and a single combined summary (generation + run) is printed

#### Scenario: Run failure surfaces a non-zero CLI exit code

- **WHEN** the underlying `RunResult.status` is `"failed"` or `"error"`
- **THEN** the CLI exits with a non-zero status so CI pipelines fail correctly

### Requirement: The runner SHALL forward test-environment variables without logging secrets

`PlaywrightRunner` SHALL pass through `TEST_USERNAME`, `TEST_PASSWORD`, and any `PLAYWRIGHT_*` environment variables to the subprocess and SHALL NOT include their values in any log line, error message, or `RunResult` field.

#### Scenario: Credentials reach the subprocess

- **WHEN** `TEST_USERNAME=alice` and `TEST_PASSWORD=secret` are set in the parent environment
- **THEN** the spawned `npx playwright test` subprocess sees both variables in its environment

#### Scenario: Credentials never appear in RunResult or logs

- **WHEN** a run completes (pass or fail) with the above credentials set
- **THEN** the strings `"alice"` and `"secret"` do not appear anywhere in `RunResult.stdout`, `RunResult.stderr`, or any log emitted by the runner
