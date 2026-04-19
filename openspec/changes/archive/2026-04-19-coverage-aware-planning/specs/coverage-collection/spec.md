## ADDED Requirements

### Requirement: A CoverageCollector SHALL produce a structured frontend coverage report

The `playwright_god.coverage.CoverageCollector` SHALL, when invoked with `frontend=True`, capture per-file JS coverage from a Chromium-based Playwright run and return a `CoverageReport` whose `source` is `"frontend"` and whose `files` dict contains one `FileCoverage` per source file referenced by the run.

#### Scenario: Frontend coverage is captured for a Chromium run

- **WHEN** `CoverageCollector(frontend=True).collect(run_callable)` wraps a Playwright run that exercises `app.js`
- **THEN** the returned `CoverageReport.source == "frontend"` and `report.files["app.js"].covered_lines > 0`

#### Scenario: Non-Chromium browser produces a warning, not a failure

- **WHEN** the wrapped run targets WebKit or Firefox and `frontend=True`
- **THEN** the call still returns a `CoverageReport` whose `files` is empty, and a warning containing `"frontend coverage requires Chromium"` is logged once

### Requirement: A CoverageCollector SHALL bracket a user-supplied backend command

When invoked with `backend_cmd="<start cmd>"`, the collector SHALL execute the start command before the Playwright run, terminate it gracefully after, and parse the resulting backend coverage artifact into a `CoverageReport` whose `source` is `"backend"`.

#### Scenario: Backend coverage is collected around a Playwright run

- **WHEN** `CoverageCollector(backend_cmd="coverage run -m uvicorn app:app").collect(run_callable)` is called
- **THEN** `coverage erase` is run before, the backend process is started, the run executes, the backend is stopped via SIGINT (then SIGTERM after timeout), `coverage json` is invoked, and the parsed file map is returned in `CoverageReport.files`

#### Scenario: Backend command failure surfaces a clear error

- **WHEN** the backend start command exits non-zero before the run begins
- **THEN** `BackendCoverageError` is raised whose message contains the failing command and its stderr tail

### Requirement: Frontend and backend reports SHALL be mergeable into a single MergedCoverageReport

The `coverage` module SHALL provide `merge(frontend, backend) -> MergedCoverageReport` whose per-file entries union the two sources without double-counting and whose top-level totals are recomputed from the merged file set.

#### Scenario: Disjoint file sets are concatenated

- **WHEN** frontend covers `["app.js"]` and backend covers `["api/users.py"]`
- **THEN** the merged report has both files and `merged.total_files == 2`

#### Scenario: Overlapping files are unioned line-wise

- **WHEN** both reports include `shared.ts` and frontend covers lines `{1,2,3}` while backend covers lines `{3,4}`
- **THEN** the merged `shared.ts` entry has `covered_lines == 4` (lines 1,2,3,4) with no double-counting

### Requirement: MemoryMap SHALL gain an optional coverage block at schema_version 2.1

`MemoryMap` SHALL accept an optional `coverage` field carrying the latest `MergedCoverageReport`, SHALL bump `schema_version` to `"2.1"` when written with coverage, and the loader SHALL accept any `2.x` schema for backward compatibility.

#### Scenario: New memory map is written with coverage

- **WHEN** `MemoryMap.with_coverage(merged_report).save(path)` is called
- **THEN** the on-disk JSON has `schema_version == "2.1"` and a `coverage` object whose `files` mirrors `merged_report.files`

#### Scenario: Older 2.0 memory map still loads

- **WHEN** a memory map written by a previous version with `schema_version == "2.0"` is loaded
- **THEN** loading succeeds and `memory_map.coverage is None`

### Requirement: The planner SHALL prioritize feature areas by uncovered size

When a memory map carries a coverage block, `playwright-god plan` SHALL order feature areas by descending count of uncovered lines (default), with `--prioritize percent` selecting descending uncovered-percentage ordering instead.

#### Scenario: Default ordering targets the biggest gap first

- **WHEN** `plan` runs against a memory map where feature `auth` has 120 uncovered lines and feature `nav` has 30 uncovered lines
- **THEN** `auth` appears before `nav` in the generated Markdown plan

#### Scenario: `--prioritize percent` switches the ordering

- **WHEN** `plan --prioritize percent` runs against a memory map where feature `auth` is at 60% covered (40% uncovered) and feature `nav` is at 20% covered (80% uncovered)
- **THEN** `nav` appears before `auth` in the generated Markdown plan

#### Scenario: Plan includes a Coverage Delta section

- **WHEN** `plan` runs with a coverage-bearing memory map
- **THEN** the output Markdown contains a `## Coverage Delta` section listing top-N gaps with file paths and line ranges

### Requirement: The generator prompt SHALL include uncovered-line excerpts as RAG context

When coverage data is present, `PlaywrightTestGenerator.generate` SHALL include up to N (default 12, configurable) uncovered line excerpts in the prompt, ranked by feature membership for the requested description.

#### Scenario: Uncovered excerpts are added to the prompt

- **WHEN** `generate "checkout flow"` is invoked with a memory map whose `checkout` feature has uncovered lines in `pay.ts:42-58` and `cart.ts:10-12`
- **THEN** the constructed prompt contains those line ranges verbatim under a `Uncovered code (gaps)` section

#### Scenario: Excerpt count is capped to protect token budget

- **WHEN** the relevant feature has 50 uncovered excerpts and the cap is the default 12
- **THEN** at most 12 excerpts appear in the prompt and a debug log line records the truncation count

### Requirement: A `coverage report` subcommand SHALL print a saved report

The CLI SHALL provide `playwright-god coverage report [--persist-dir DIR] [--format text|json|html]` that loads the most recent merged coverage report from the persist dir and prints it without re-running tests.

#### Scenario: Default text report is printed

- **WHEN** `playwright-god coverage report` is invoked with a saved report present
- **THEN** a per-file table is printed to stdout with columns `file`, `covered`, `total`, `percent`

#### Scenario: Missing report exits with a non-zero status and a clear message

- **WHEN** the command runs in a persist dir with no saved coverage report
- **THEN** the CLI exits non-zero and prints a message containing `"no coverage report found"` and instructions to run `playwright-god generate ... --run --coverage`
