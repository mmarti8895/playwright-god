## ADDED Requirements

### Requirement: Index-only orchestration
The desktop application SHALL provide a dedicated "Run Index" action that, against the active repository, runs only the CLI `index` step, streams stdout and stderr into the existing output pane, supports cancellation through the existing pipeline controls, and refreshes index-backed viewers when the step finishes successfully.

#### Scenario: User runs index without full pipeline
- **WHEN** the user clicks "Run Index" for an active repository
- **THEN** the desktop app starts an index-only run, streams the `index` step output in real time, and does not start `plan`, `generate`, or `run`

#### Scenario: Index-only run refreshes dependent viewers
- **WHEN** an index-only run finishes successfully
- **THEN** the Memory Map and RAG views can immediately read the refreshed artifacts without requiring an app restart
