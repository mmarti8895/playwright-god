## 1. Coverage module

- [x] 1.1 Create `playwright_god/coverage.py` with `FileCoverage`, `CoverageReport`, `MergedCoverageReport`, `BackendCoverageError`
- [x] 1.2 Implement `CoverageCollector(frontend=True/False, backend_cmd=...)`
- [x] 1.3 Implement `merge(frontend, backend) -> MergedCoverageReport` with line-set union semantics
- [x] 1.4 Bundle `playwright_god/_assets/coverage_fixture.ts` and a loader helper

## 2. Runner integration

- [x] 2.1 Add `coverage: bool = False` and `coverage_collector` plumbing to `PlaywrightRunner`
- [x] 2.2 Inject the JS fixture via spec import or `playwright.config.ts` patch (idempotent)
- [x] 2.3 Detect non-Chromium projects and emit the structured warning
- [x] 2.4 Populate `RunResult.coverage_raw` and pipe it to the collector

## 3. Memory map schema 2.1

- [x] 3.1 Add optional `coverage` field to `MemoryMap` and bump default `schema_version` to `"2.1"`
- [x] 3.2 Extend the loader to accept `2.x` schemas; default `coverage = None` when absent
- [x] 3.3 Add `MemoryMap.with_coverage(report)` and round-trip JSON tests

## 4. Planner & generator

- [x] 4.1 In `plan`, sort feature areas by uncovered-lines (default) or uncovered-percent (`--prioritize percent`)
- [x] 4.2 Emit a `## Coverage Delta` section in the generated Markdown
- [x] 4.3 In `generate`, append an `Uncovered code (gaps)` block to the prompt with a configurable cap (default 12 excerpts)

## 5. CLI

- [x] 5.1 Add `--coverage` and `--backend-coverage <cmd>` flags to `generate` and the new `run` subcommand
- [x] 5.2 Add `playwright-god coverage report [--format text|json|html]` subcommand (read-only)
- [x] 5.3 Add `--prioritize percent|absolute` to `plan`

## 6. Tests

- [x] 6.1 `tests/unit/test_coverage.py`: collector unit tests with mocked subprocess + Chromium payloads
- [x] 6.2 `tests/fixtures/coverage_sample.json`: realistic frontend + backend payloads
- [x] 6.3 `tests/unit/test_memory_map.py`: 2.0 → 2.1 round-trip + backward compatibility
- [x] 6.4 `tests/unit/test_generator.py`: prompt contains uncovered excerpts when present, capped correctly
- [x] 6.5 `tests/integration/test_coverage_pipeline.py`: end-to-end against `tests/fixtures/sample_app/` (gated by `requires_node`)
- [x] 6.6 `tests/unit/test_cli.py`: new flags + `coverage report` subcommand

## 7. Docs & polish

- [x] 7.1 README "Coverage-driven workflow" section with prerequisites + examples
- [x] 7.2 README Memory Map section: bump example to `schema_version: "2.1"` and add `coverage` block
- [x] 7.3 Add `[coverage]` extra to `pyproject.toml` (`coverage>=7`)
- [x] 7.4 Verify `pytest --cov=playwright_god` ≥ 99% with the new module
