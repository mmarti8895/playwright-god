## ADDED Requirements

### Requirement: Repository selection
The desktop application SHALL allow the user to select a target repository via a native folder-picker dialog and SHALL validate that the selected path exists and is a directory before activating it.

#### Scenario: Valid repository selected
- **WHEN** the user clicks "Open Repository" and selects an existing directory
- **THEN** the directory becomes the active repository, its absolute path is shown in the header, and it is prepended to the recent-repositories list

#### Scenario: Invalid path supplied
- **WHEN** the user supplies a path that does not exist or is not a directory
- **THEN** the app surfaces an inline error message and does not change the active repository

### Requirement: Pipeline orchestration
The desktop application SHALL provide a single "Run Pipeline" action that, against the active repository, runs the equivalent of `index → memory-map → flow-graph → plan → generate → run` by spawning the `playwright-god` CLI as subprocesses and SHALL stream stdout and stderr line-by-line into the output pane.

#### Scenario: Full pipeline run
- **WHEN** the user clicks "Run Pipeline" with an active repository
- **THEN** the CLI subprocesses execute in dependency order, each step's output is streamed to the output pane in real time, and a step is not started until the previous step exits successfully

#### Scenario: Step failure aborts the pipeline
- **WHEN** any pipeline step exits with a non-zero status
- **THEN** subsequent steps are not started, the failure is highlighted in the output pane, and the run is marked failed in the audit log

### Requirement: Progress reporting
The desktop application SHALL display a progress bar for the active pipeline run that advances when each step starts and completes, and SHALL show the current step name and elapsed time.

#### Scenario: Progress advances per step
- **WHEN** a pipeline run is in progress
- **THEN** the progress bar shows discrete advancement at the start and completion of each step and the current step name is visible

### Requirement: Cancellation
The desktop application SHALL allow the user to cancel an in-flight pipeline run, which SHALL terminate the active CLI subprocess and SHALL not start subsequent steps.

#### Scenario: User cancels mid-run
- **WHEN** the user clicks "Cancel" while a pipeline run is in progress
- **THEN** the active subprocess receives a termination signal, the output pane shows a "cancelled" marker, and the audit log records the run as cancelled

### Requirement: Per-run artifact discovery
The desktop application SHALL, after each run, discover and index the artifacts written under `<repo>/.pg_runs/<timestamp>/` (run summary, evaluation report, coverage merged, prompt transcripts) and make them available to the artifact viewers without requiring an app restart.

#### Scenario: New run artifacts are visible
- **WHEN** a pipeline run completes and writes artifacts under `.pg_runs/<timestamp>/`
- **THEN** the new run appears at the top of the Audit Log section and its artifacts are loadable by the relevant viewers

### Requirement: Settings flow into CLI invocations
The desktop application SHALL pass the user's configured LLM provider, model, API key, Ollama URL, and Playwright-CLI timeout to every CLI invocation either via environment variables (`PLAYWRIGHT_GOD_PROVIDER`, `PLAYWRIGHT_GOD_MODEL`, `OPENAI_API_KEY`, etc.) or via the corresponding CLI flags.

#### Scenario: Provider override is honored
- **WHEN** the user sets the provider to `template` in Settings and runs the pipeline
- **THEN** the spawned CLI subprocesses receive `PLAYWRIGHT_GOD_PROVIDER=template` (or the equivalent flag) and use the offline template generator

### Requirement: Codegen stream toggle
The desktop application SHALL expose a checkbox in the Codegen Stream section that, when enabled, live-tails the LLM prompt and response transcripts and the `playwright codegen` output as they are produced during a pipeline run.

#### Scenario: Stream enabled mid-run
- **WHEN** the user enables the codegen-stream checkbox during a run
- **THEN** subsequent prompt/response and codegen lines for that run are appended to the Codegen Stream view in real time
