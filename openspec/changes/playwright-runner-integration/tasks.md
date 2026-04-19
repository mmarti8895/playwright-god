## 1. Runner module

- [x] 1.1 Create `playwright_god/runner.py` with `RunResult`, `TestCaseResult` dataclasses and `RunnerSetupError`
- [x] 1.2 Implement `PlaywrightRunner.check_environment()` (npx + package.json + `@playwright/test` detection)
- [x] 1.3 Implement `PlaywrightRunner.run(spec_path)` using `subprocess.run` with the JSON reporter
- [x] 1.4 Implement working-directory resolution (walk up to nearest `package.json`, honor `--target-dir`)
- [x] 1.5 Implement artifact directory layout (`<artifact_dir>/<timestamp>/`)
- [x] 1.6 Implement env passthrough for `TEST_USERNAME`, `TEST_PASSWORD`, `PLAYWRIGHT_*`

## 2. CLI integration

- [x] 2.1 Add `playwright-god run <spec-or-dir>` subcommand in `cli.py`
- [x] 2.2 Add `--run`, `--target-dir`, `--reporter`, `--artifact-dir` flags on the new subcommand
- [x] 2.3 Add `--run` flag to existing `generate` command and chain generation → execution
- [x] 2.4 Map `RunResult.exit_code` to the CLI process exit code

## 3. Tests

- [x] 3.1 `tests/unit/test_runner.py`: mock `subprocess.run` for passed/failed/error paths
- [x] 3.2 `tests/unit/test_runner.py`: cover all `RunnerSetupError` branches (no npx, no package.json, missing dep)
- [x] 3.3 `tests/unit/test_runner.py`: secret-redaction assertions (`TEST_USERNAME`/`TEST_PASSWORD` never in result)
- [x] 3.4 `tests/fixtures/playwright_report_sample.json`: capture a real reporter sample for regression
- [x] 3.5 `tests/integration/test_runner_pipeline.py`: end-to-end against `tests/fixtures/sample_app/`, gated by `requires_node` marker
- [x] 3.6 `tests/unit/test_cli.py`: cover new `run` subcommand and `generate --run` flag

## 4. Documentation & polish

- [x] 4.1 README: new "Running generated tests" section with prerequisites and examples
- [x] 4.2 README: update Coverage table once new module lands
- [x] 4.3 Update `AGENTS.md` (if present) to note the new `run` capability
- [x] 4.4 Verify `pytest --cov=playwright_god` still ≥ 99% with the new module included
