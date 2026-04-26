## MODIFIED Requirements

### Requirement: Pipeline orchestration
The desktop application SHALL provide a single "Run Pipeline" action that, against the active repository, runs the equivalent of `index → memory-map → flow-graph → plan → generate → run` by spawning the `playwright-god` CLI as subprocesses and SHALL stream stdout and stderr line-by-line into the output pane.

#### Scenario: Full pipeline run
- **WHEN** the user clicks "Run Pipeline" with an active repository
- **THEN** the CLI subprocesses execute in dependency order, each step's output is streamed to the output pane in real time, and a step is not started until the previous step exits successfully

#### Scenario: Step failure aborts the pipeline
- **WHEN** any pipeline step exits with a non-zero status
- **THEN** subsequent steps are not started, the failure is highlighted in the output pane, and the run is marked failed in the audit log

#### Scenario: Generation uses section description context
- **WHEN** the user runs the pipeline from the Generation section with a non-empty description
- **THEN** that description is passed into generation orchestration for the active run and the run state is reflected through existing progress, status, and cancellation controls

### Requirement: Per-run artifact discovery
The desktop application SHALL, after each run, discover and index the artifacts written under `<repo>/.pg_runs/<timestamp>/` (run summary, evaluation report, coverage merged, prompt transcripts) and make them available to the artifact viewers without requiring an app restart.

#### Scenario: New run artifacts are visible
- **WHEN** a pipeline run completes and writes artifacts under `.pg_runs/<timestamp>/`
- **THEN** the new run appears at the top of the Audit Log section and its artifacts are loadable by the relevant viewers

#### Scenario: Viewer refresh after generation-related runs
- **WHEN** a run that updates coverage or index artifacts completes successfully
- **THEN** Coverage & Gaps, RAG Search, and Generation-adjacent artifact consumers can read the latest artifacts on next render without manual app restart
