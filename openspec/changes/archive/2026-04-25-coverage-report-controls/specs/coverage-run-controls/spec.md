# Coverage Run Controls

## Purpose

Defines the requirements for triggering, monitoring, cancelling, and clearing a coverage report run directly from the Coverage & Gaps section of the desktop application.

## ADDED Requirements

### Requirement: User can trigger a coverage run from the UI

The Coverage & Gaps section SHALL provide a **Run Coverage** button that invokes `playwright-god run <last_spec> --coverage` on the active repository. The button SHALL be disabled when no repository is active, when no previously generated spec exists in `.pg_runs/`, or when the main pipeline is actively running on the same repository.

#### Scenario: Run button triggers subprocess

- **WHEN** the user clicks **Run Coverage** with an active repo and an existing generated spec
- **THEN** the Tauri backend spawns `playwright-god run <spec_path> --coverage` and emits a `RunStarted` event containing the resolved spec path

#### Scenario: Run button disabled with no spec

- **WHEN** the active repository has no `.pg_runs/` directory or no `generated.spec.ts` inside it
- **THEN** the **Run Coverage** button is disabled and a tooltip reads "No generated spec found. Run the full pipeline first."

#### Scenario: Run button disabled during active pipeline

- **WHEN** the main pipeline is actively running on the current repository
- **THEN** the **Run Coverage** button is disabled and a tooltip reads "Pipeline is running. Wait for it to finish."

---

### Requirement: Live progress is displayed during a coverage run

The Coverage & Gaps section SHALL display a log panel showing stdout/stderr lines streamed from the subprocess in real time. The panel SHALL be visible while status is `running` and remain visible (collapsed by default) after status transitions to `done` or `error`.

#### Scenario: Log lines appear during run

- **WHEN** the coverage subprocess writes a line to stdout or stderr
- **THEN** that line appears in the log panel within one render cycle, appended at the bottom

#### Scenario: Log buffer is capped

- **WHEN** the number of log lines exceeds 500
- **THEN** the oldest lines are dropped so the buffer never exceeds 500 entries

#### Scenario: Log panel is collapsed after success

- **WHEN** the run finishes with exit code 0
- **THEN** the log panel collapses automatically and the coverage report display refreshes

---

### Requirement: User can cancel an in-progress coverage run

The Coverage & Gaps section SHALL display a **Cancel** button while `status === "running"`. Clicking it SHALL terminate the subprocess and transition status to `idle`.

#### Scenario: Cancel terminates the subprocess

- **WHEN** the user clicks **Cancel** during an active run
- **THEN** the Tauri backend kills the child process, emits `Cancelled`, and the UI status transitions to `idle`

#### Scenario: Partial results message on cancel

- **WHEN** the run is cancelled
- **THEN** the log panel displays "Run cancelled — partial coverage results may exist in .pg_runs/"

---

### Requirement: User can clear results to enable a re-run

The Coverage & Gaps section SHALL display a **Clear** button when `status === "done"` or `status === "error"`. Clicking it SHALL reset the in-memory report and run log, returning the section to the empty-state prompt so the user can trigger a fresh run.

#### Scenario: Clear resets UI to empty state

- **WHEN** the user clicks **Clear** after a completed run
- **THEN** the coverage report display resets to the "No coverage report yet" empty state and the log panel is hidden

#### Scenario: Clear does not delete files on disk

- **WHEN** the user clicks **Clear**
- **THEN** no files are deleted from `.pg_runs/`; only in-memory UI state is reset

---

### Requirement: Coverage display auto-refreshes after a successful run

After a coverage run completes with exit code 0, the Coverage & Gaps section SHALL automatically reload coverage data from the newly written `coverage_merged.json` without requiring a manual refresh.

#### Scenario: Report refreshes on run completion

- **WHEN** the coverage subprocess exits with code 0
- **THEN** `artifactsVersion` is bumped, triggering `readCoverage` to fetch the new `coverage_merged.json`, and the report tiles update within one render cycle
