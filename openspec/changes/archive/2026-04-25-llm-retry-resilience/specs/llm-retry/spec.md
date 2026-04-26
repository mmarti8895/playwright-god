## ADDED Requirements

### Requirement: Retry policy for transient LLM failures
The CLI SHALL automatically retry LLM provider calls that fail with a transient network error (identified by exit code 2 / `upstream-network` diagnostic tag) using exponential backoff with full jitter, up to a configurable maximum number of attempts.

#### Scenario: Retry on transient network error
- **WHEN** a `plan` or `generate` step exits with code 2
- **THEN** the CLI waits for the computed backoff delay and re-attempts the LLM call, up to `--retry-max` times (default 3)

#### Scenario: Immediate failure on non-network errors
- **WHEN** a `plan` or `generate` step exits with code 1 (e.g., invalid API key, quota exceeded)
- **THEN** the CLI does NOT retry and propagates the failure immediately

#### Scenario: All retries exhausted
- **WHEN** all retry attempts fail with exit code 2
- **THEN** the CLI exits with code 2 and emits a final `[pg:retry] exhausted attempts=<n>` line to stderr

### Requirement: Retry configuration via CLI flags and environment
The `plan` and `generate` CLI commands SHALL accept `--retry-max <int>` (default 3) and `--retry-delay <float>` (initial backoff seconds, default 2.0). The environment variables `PLAYWRIGHT_GOD_RETRY_MAX` and `PLAYWRIGHT_GOD_RETRY_DELAY_S` SHALL serve as fallback configuration when the flags are not provided.

#### Scenario: Flag overrides environment variable
- **WHEN** `PLAYWRIGHT_GOD_RETRY_MAX=5` is set and `--retry-max 1` is passed
- **THEN** the effective max is 1 (flag wins)

#### Scenario: Environment variable used when no flag provided
- **WHEN** `PLAYWRIGHT_GOD_RETRY_DELAY_S=10` is set and no `--retry-delay` flag is passed
- **THEN** the effective initial delay is 10 seconds

#### Scenario: Disable retries with zero
- **WHEN** `--retry-max 0` is passed
- **THEN** no retry is attempted; the first failure propagates immediately

### Requirement: Retry progress emitted to stderr
The CLI SHALL emit a structured line to stderr before each retry attempt using the format `[pg:retry] attempt=<n>/<max> delay=<s>`, allowing callers to parse retry progress without coupling to log message wording.

#### Scenario: Retry line is emitted before each attempt
- **WHEN** the first attempt fails and a retry is scheduled
- **THEN** stderr contains `[pg:retry] attempt=2/<max> delay=<s>` before the second attempt begins

#### Scenario: Exhausted line is emitted on final failure
- **WHEN** all attempts are exhausted
- **THEN** stderr contains `[pg:retry] exhausted attempts=<max>`

### Requirement: Backoff uses exponential delay with full jitter
The retry delay SHALL follow `min(base * 2^(attempt-1) + uniform(0, base), 60)` seconds, where `base` is the configured initial delay.

#### Scenario: Delay grows exponentially
- **WHEN** the initial delay is 2 s and three retries occur
- **THEN** the delays are approximately 2 s, 4 s, and 8 s (before jitter), each capped at 60 s
