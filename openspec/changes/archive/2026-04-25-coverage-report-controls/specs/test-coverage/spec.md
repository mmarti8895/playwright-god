# Test Coverage (delta)

## Purpose

Delta spec for the `test-coverage` capability. The core read-only display requirements are unchanged. This file captures the requirement additions that arise from the coverage-run-controls change — specifically, the new interaction states of the Coverage & Gaps view.

## ADDED Requirements

### Requirement: Coverage & Gaps view supports run lifecycle states

The Coverage & Gaps view SHALL implement a four-state lifecycle: `idle` (no report, no active run), `running` (subprocess active), `done` (report loaded), and `error` (run failed or report unreadable). Visual affordances SHALL match the current state at all times.

#### Scenario: Idle state shows empty-state prompt with Run button

- **WHEN** no coverage report exists and no run is in progress
- **THEN** the view shows the "No coverage report yet" empty-state message AND a enabled **Run Coverage** button

#### Scenario: Running state shows progress log and Cancel button

- **WHEN** a coverage run is in progress
- **THEN** the view shows the live log panel, a **Cancel** button, and hides the run/clear buttons

#### Scenario: Done state shows report and Clear button

- **WHEN** a coverage run finishes successfully and the report is loaded
- **THEN** the view shows the full coverage report (totals header + tabs) and a **Clear** button in the toolbar

#### Scenario: Error state shows error message and Run button

- **WHEN** a coverage run exits with a non-zero code or the report file is unreadable
- **THEN** the view shows the error message from the log AND re-enables the **Run Coverage** button so the user can retry
