# Pipeline Orchestration

## Purpose

Capability added by the `tauri-desktop-ui` change (archived). See the change for the original proposal and design notes.
## Requirements
### Requirement: Repository selection
The desktop application SHALL allow the user to select a target repository via a native folder-picker dialog and SHALL validate that the selected path exists and is a directory before activating it.

#### Scenario: Valid repository selected
- **WHEN** the user clicks "Open Repository" and selects an existing directory
- **THEN** the directory becomes the active repository, its absolute path is shown in the header, and it is prepended to the recent-repositories list

#### Scenario: Invalid path supplied
- **WHEN** the user supplies a path that does not exist or is not a directory
- **THEN** the app surfaces an inline error message and does not change the active repository

### Requirement: Repository indexing controls
The Repository section SHALL show the active repository's indexing status and SHALL expose a dedicated "Run Index" action alongside the existing full-pipeline workflow.

#### Scenario: Repository shows missing-index state
- **WHEN** the user selects a repository that does not yet have index artifacts
- **THEN** the Repository section shows that indexing is required and enables a "Run Index" action for that repository

#### Scenario: Repository shows active indexing state
- **WHEN** an index-only run is in progress for the active repository
- **THEN** the Repository section reflects that indexing is running and the action state matches the active run controls

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

#### Scenario: Viewer refresh after generation-related runs
- **WHEN** a run that updates coverage or index artifacts completes successfully
- **THEN** Coverage & Gaps, RAG Search, and Generation-adjacent artifact consumers can read the latest artifacts on next render without manual app restart

### Requirement: Settings flow into CLI invocations
The desktop application SHALL pass the user's configured LLM provider, model, API key, Ollama URL, and Playwright-CLI timeout to every CLI invocation either via environment variables (`PLAYWRIGHT_GOD_PROVIDER`, `PLAYWRIGHT_GOD_MODEL`, `OPENAI_API_KEY`, etc.) or via the corresponding CLI flags.

#### Scenario: Provider override is honored
- **WHEN** the user sets the provider to `template` in Settings and runs the pipeline
- **THEN** the spawned CLI subprocesses receive `PLAYWRIGHT_GOD_PROVIDER=template` (or the equivalent flag) and use the offline template generator

#### Scenario: Plan step receives OpenAI runtime settings
- **WHEN** provider=`openai`, model=`gpt-5.4`, and an OpenAI key source is available
- **THEN** the `plan` step subprocess is spawned with `PLAYWRIGHT_GOD_PROVIDER=openai`, `PLAYWRIGHT_GOD_MODEL=gpt-5.4`, and `OPENAI_API_KEY` present in its runtime environment

### Requirement: Codegen stream toggle
The desktop application SHALL expose a checkbox in the Codegen Stream section that, when enabled, live-tails the LLM prompt and response transcripts and the `playwright codegen` output as they are produced during a pipeline run.

#### Scenario: Stream enabled mid-run
- **WHEN** the user enables the codegen-stream checkbox during a run
- **THEN** subsequent prompt/response and codegen lines for that run are appended to the Codegen Stream view in real time

### Requirement: LLM connectivity diagnostics for LLM-dependent steps
The desktop pipeline orchestrator SHALL emit classified diagnostics for LLM-dependent steps (`plan`, `generate`) so users can distinguish configuration issues from upstream/API/network failures.

#### Scenario: Missing OpenAI key fails fast with actionable message
- **WHEN** provider=`openai` is selected and no effective `OPENAI_API_KEY` source is available at plan-step start
- **THEN** the run fails that step with a clear configuration diagnostic describing the missing key source and next actions

#### Scenario: Upstream/API error is classified distinctly
- **WHEN** the `plan` step exits non-zero due to OpenAI auth/quota/network response errors
- **THEN** the run output classifies the failure as upstream/API connectivity rather than local settings absence

### Requirement: Fused graph artifact preparation
The desktop pipeline/artifact layer SHALL prepare a fused graph model from flow-graph and memory-map artifacts for the active repository and SHALL refresh this model after successful index-related runs.

#### Scenario: Fused graph refresh after indexing
- **WHEN** an index-only or full pipeline run completes successfully for the active repository
- **THEN** the fused graph inputs are refreshed so the Flow Graph section can render updated cross-entity connectivity without requiring app restart

#### Scenario: Deterministic fused graph identity
- **WHEN** fused graph nodes and edges are composed from artifacts
- **THEN** node and edge identities remain stable across refreshes when source artifact content is unchanged

### Requirement: Optional embedded graph-cache mode
The desktop application SHALL support an optional lightweight embedded open-source graph-cache mode for fused-graph queries on large repositories while keeping in-memory composition as the default mode.

#### Scenario: Default mode remains dependency-light
- **WHEN** the user has not enabled graph-cache mode
- **THEN** fused graph composition runs in-memory with no required external graph database runtime

#### Scenario: Graph-cache mode is used when enabled
- **WHEN** graph-cache mode is enabled and repository graph size exceeds configured thresholds
- **THEN** the app materializes/queries the fused graph via the embedded graph-cache backend and preserves viewer behavior parity with in-memory mode

### Requirement: RetryAttempt pipeline event
The pipeline orchestrator SHALL emit a `RetryAttempt` event to the frontend when a `[pg:retry]` line is detected in the stderr stream of a `plan` or `generate` step, carrying the step name, attempt number, max attempts, and planned delay.

#### Scenario: RetryAttempt event emitted on retry line
- **WHEN** the `plan` subprocess emits `[pg:retry] attempt=2/3 delay=4.3` to stderr
- **THEN** the orchestrator emits `PipelineEvent::RetryAttempt { step: "plan", attempt: 2, max: 3, delay_s: 4.3 }` through the frontend channel

#### Scenario: RetryAttempt does not suppress the raw stderr line
- **WHEN** a `[pg:retry]` line is received
- **THEN** both the `RetryAttempt` event AND a `StderrLine` event are emitted so the raw log remains complete

### Requirement: Retry flags forwarded to plan and generate steps
The orchestrator SHALL append `--retry-max <n>` and `--retry-delay <s>` to the subprocess args for the `plan` and `generate` steps, reading the values from the desktop settings.

#### Scenario: Settings values forwarded as CLI flags
- **WHEN** settings contain `llm_retry_max=2` and `llm_retry_delay_s=5.0`
- **THEN** the `plan` and `generate` subprocesses are invoked with `--retry-max 2 --retry-delay 5.0`

#### Scenario: Default values used when settings not customised
- **WHEN** no retry settings are configured by the user
- **THEN** the subprocesses receive `--retry-max 3 --retry-delay 2.0`

### Requirement: Index persistence respects ChromaDB max batch size
The index step SHALL split vector-store upserts into bounded batches so no single ChromaDB upsert exceeds the backend-reported max batch size.

#### Scenario: Oversized payload is split before upsert
- **WHEN** the index step prepares an upsert payload larger than the active ChromaDB max batch size
- **THEN** the payload is partitioned into multiple upserts and each issued upsert size is less than or equal to the max batch size

#### Scenario: Large repository index completes without batch-limit crash
- **WHEN** indexing a repository that would previously trigger `Batch size ... greater than max batch size ...`
- **THEN** the index step completes successfully without emitting an oversized-batch failure

### Requirement: Batch-limit resilience is covered by regression tests
The Python test suite SHALL include regression tests for oversized upsert payloads to prevent recurrence of ChromaDB batch-limit failures.

#### Scenario: Regression test reproduces pre-fix oversized case
- **WHEN** a test injects index data exceeding a representative max batch threshold
- **THEN** the test verifies the persistence layer performs multiple bounded upserts instead of one oversized call

#### Scenario: Regression test fails if bounded upsert protection is removed
- **WHEN** bounded upsert logic is bypassed or disabled
- **THEN** the regression test fails with an assertion indicating an oversized upsert attempt was made

