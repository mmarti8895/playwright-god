## Why

LLM-dependent pipeline steps (`plan`, `generate`) fail permanently on transient network errors — a single connection blip aborts the entire pipeline run with no recovery. Users see `FAIL plan: step 'plan' exited with code 2` and must restart manually, losing all progress from earlier steps.

## What Changes

- Add configurable exponential-backoff retry logic to the Python CLI for LLM provider calls (`plan`, `generate`, and any step that exits with the upstream-network diagnostic code 2).
- Expose retry count and initial delay as environment variables (`PLAYWRIGHT_GOD_RETRY_MAX`, `PLAYWRIGHT_GOD_RETRY_DELAY_S`) and optional CLI flags (`--retry-max`, `--retry-delay`).
- Add a retry setting to the desktop app Settings UI so users can configure without editing env vars.
- Stream retry attempt events through the existing Tauri `Channel<PipelineEvent>` so the UI shows "Retrying (attempt 2/3)…" instead of a blank stream.
- Detect the specific `upstream-network` exit-code (2) to limit retries to transient errors only; non-network failures (bad API key, quota exceeded, invalid prompt) fail immediately.
- Add a **BREAKING** change: the `generate` and `plan` CLI commands gain `--retry-max` / `--retry-delay` flags that override global config.

## Capabilities

### New Capabilities

- `llm-retry`: Retry policy for LLM-dependent CLI steps — configurable max attempts, exponential backoff with jitter, upstream-network-only guard, and streaming retry-progress events.

### Modified Capabilities

- `pipeline-orchestration`: The desktop pipeline orchestrator must forward retry-attempt events to the frontend and include the new retry CLI flags when spawning `plan` and `generate` steps.
- `desktop-settings`: The Settings schema gains `llm_retry_max` (integer, default 3) and `llm_retry_delay_s` (float, default 2.0) fields surfaced in the Settings UI.

## Impact

- **Python CLI** (`playwright_god/cli.py`, `playwright_god/generator.py`, new `playwright_god/retry.py`): retry wrapper around provider calls.
- **Tauri backend** (`desktop/src-tauri/src/pipeline.rs`, `desktop/src-tauri/src/settings.rs`): new settings fields, new `PipelineEvent::RetryAttempt` variant, flags forwarded to subprocess.
- **Frontend** (`desktop/src/lib/settings.ts`, `desktop/src/sections/Settings.tsx`, `desktop/src/state/pipeline.ts`): new settings fields, retry-attempt event handling, UI feedback.
- **No schema-level breakage** to existing stored data — new settings fields default gracefully.
