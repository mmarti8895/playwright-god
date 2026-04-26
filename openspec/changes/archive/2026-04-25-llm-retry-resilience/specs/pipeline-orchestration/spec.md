## ADDED Requirements

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
