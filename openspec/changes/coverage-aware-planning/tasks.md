## 1. Coverage module

- [ ] 1.1 Create `playwright_god/coverage.py` with `FileCoverage`, `CoverageReport`, `MergedCoverageReport`, `BackendCoverageError`
- [ ] 1.2 Implement `CoverageCollector(frontend=True/False, backend_cmd=...)`
- [ ] 1.3 Implement `merge(frontend, backend) -> MergedCoverageReport` with line-set union semantics
- [ ] 1.4 Bundle `playwright_god/_assets/coverage_fixture.ts` and a loader helper

## 2. Runner integration

- [ ] 2.1 Add `coverage: bool = False` and `coverage_collector` plumbing to `PlaywrightRunner`
- [ ] 2.2 Inject the JS fixture via spec import or `playwright.config.ts` patch (idempotent)
- [ ] 2.3 Detect non-Chromium projects and emit the structured warning
- [ ] 2.4 Populate `RunResult.coverage_raw` and pipe it to the collector

## 3. Memory map schema 2.1

- [ ] 3.1 Add optional `coverage` field to `MemoryMap` and bump default `schema_version` to `"2.1"`
- [ ] 3.2 Extend the loader to accept `2.x` schemas; default `coverage = None` when absent
- [ ] 3.3 Add `MemoryMap.with_coverage(report)` and round-trip JSON tests

## 4. Planner & generator

- [ ] 4.1 In `plan`, sort feature areas by uncovered-lines (default) or uncovered-percent (`--prioritize percent`)
- [ ] 4.2 Emit a `## Coverage Delta` section in the generated Markdown
- [ ] 4.3 In `generate`, append an `Uncovered code (gaps)` block to the prompt with a configurable cap (default 12 excerpts)

## 5. CLI

- [ ] 5.1 Add `--coverage` and `--backend-coverage <cmd>` flags to `generate` and the new `run` subcommand
- [ ] 5.2 Add `playwright-god coverage report [--format text|json|html]` subcommand (read-only)
- [ ] 5.3 Add `--prioritize percent|absolute` to `plan`

## 6. Tests

- [ ] 6.1 `tests/unit/test_coverage.py`: collector unit tests with mocked subprocess + Chromium payloads
- [ ] 6.2 `tests/fixtures/coverage_sample.json`: realistic frontend + backend payloads
- [ ] 6.3 `tests/unit/test_memory_map.py`: 2.0 → 2.1 round-trip + backward compatibility
- [ ] 6.4 `tests/unit/test_generator.py`: prompt contains uncovered excerpts when present, capped correctly
- [ ] 6.5 `tests/integration/test_coverage_pipeline.py`: end-to-end against `tests/fixtures/sample_app/` (gated by `requires_node`)
- [ ] 6.6 `tests/unit/test_cli.py`: new flags + `coverage report` subcommand

## 7. Docs & polish

- [ ] 7.1 README "Coverage-driven workflow" section with prerequisites + examples
- [ ] 7.2 README Memory Map section: bump example to `schema_version: "2.1"` and add `coverage` block
- [ ] 7.3 Add `[coverage]` extra to `pyproject.toml` (`coverage>=7`)
- [ ] 7.4 Verify `pytest --cov=playwright_god` ≥ 99% with the new module
