## Context

The `playwright-god` pipeline chains LLM-dependent steps (`plan`, `generate`) that call external APIs. When a transient network error occurs (VPN dropped, DNS blip, provider rate-limit), the CLI exits with code 2 and the diagnostic tag `upstream-network`. The desktop app treats any non-zero exit as a permanent failure and aborts the run. Users lose all progress and must restart from scratch.

The existing CLI already distinguishes `upstream-network` exits (code 2) from logic errors (code 1) in the diagnostic output. The Tauri pipeline runner spawns subprocesses per step and streams events; it has no retry awareness today.

Constraints:
- Retry must not apply to deterministic failures (bad API key, quota exceeded, invalid input) — only to transient ones identified by exit code 2.
- Must not introduce new mandatory dependencies (no `tenacity` or similar heavy libs forced on all users).
- Retry progress must be visible in the desktop UI — users should not see a frozen stream.
- Configuration must be optional and backward-compatible (default: 3 retries, 2 s initial delay).

## Goals / Non-Goals

**Goals:**
- Automatic retry with exponential backoff for `plan` and `generate` steps when the CLI exits with code 2 (`upstream-network`).
- Configurable max retries and initial delay via env vars, CLI flags, and desktop Settings UI.
- `PipelineEvent::RetryAttempt` event variant streamed to the frontend with attempt number and delay.
- Desktop Settings gains `llm_retry_max` (int, default 3) and `llm_retry_delay_s` (float, default 2.0) fields, forwarded as CLI flags.
- Jitter on backoff delay to avoid thundering-herd when multiple users retry simultaneously.
- Unit tests: retry wrapper in Python, Rust event variant serialization, Settings validation.

**Non-Goals:**
- Retry for the `index`, `flow-graph`, `plan`, or `run` steps — these are not LLM-dependent and their failures are typically not transient.
- Circuit-breaker or provider-failover (switching from OpenAI to Anthropic on failure).
- Per-step retry configuration — all retryable steps share the same policy.
- UI "pause and resume" — retry happens automatically without user interaction.
- Retry for the standalone `playwright-god run` (coverage) command — only the pipeline steps.

## Decisions

### D1 — Retry lives in the Python CLI, not the Tauri runner

**Decision:** Implement the retry loop inside the Python CLI (`playwright_god/retry.py`) rather than at the Tauri subprocess level.

**Rationale:** The CLI already has access to the provider error type, can inspect the response, and the exit-code contract (code 2 = transient) is already documented. Retrying at the Tauri level would require re-spawning the whole subprocess and losing partial stdout. Retrying inside the CLI lets us retry only the LLM call itself, preserving any work done in the same step before the call.

**Alternative:** Tauri re-spawns the subprocess on exit code 2. Rejected — coarser, harder to pass context, and loses stdout already streamed.

### D2 — Exponential backoff with full jitter

**Decision:** Use `delay * 2^(attempt-1) + uniform(0, delay)` capped at 60 s.

**Rationale:** Full jitter (per AWS: "Exponential Backoff and Jitter") avoids correlated retries across concurrent users. A cap of 60 s is aggressive enough to recover before most CI timeouts.

**Alternative:** Fixed delay. Rejected — floods the provider during an outage.

### D3 — New `PipelineEvent::RetryAttempt` Tauri event variant

**Decision:** Add a new variant to the existing `PipelineEvent` enum rather than overloading `StdoutLine`/`StderrLine`.

**Rationale:** Typed variants let the frontend handle retry UI distinctly (e.g., a spinner annotation vs. raw log text). Keeps the event schema clean.

**Alternative:** Emit a specially-prefixed stderr line (`[RETRY] attempt 2/3`). Rejected — fragile text parsing.

### D4 — Retry flags forwarded by Tauri as CLI arguments

**Decision:** Tauri reads `llm_retry_max` and `llm_retry_delay_s` from Settings and appends `--retry-max N --retry-delay S` to the `plan` and `generate` subprocess args.

**Rationale:** Keeps configuration source-of-truth in the desktop settings store. No need for env-var injection for retry (avoids polluting the env passed to the repo's own processes).

**Alternative:** Env vars `PLAYWRIGHT_GOD_RETRY_MAX` / `PLAYWRIGHT_GOD_RETRY_DELAY_S`. Retained as a secondary fallback for headless CLI users.

### D5 — Retry events emitted by CLI via stderr with structured prefix

**Decision:** The CLI emits `[pg:retry] attempt=2 delay=4.3` lines to stderr. Tauri parses these to synthesize `RetryAttempt` events without requiring a new IPC channel.

**Rationale:** Reuses the existing stderr-reading loop. Structured prefix avoids ambiguity with normal log lines. No new IPC surface.

**Alternative:** A separate JSON-events channel. Rejected — over-engineered for one event type.

## Risks / Trade-offs

- **[Risk] Retry masks persistent errors** → Mitigation: Only retry on exit code 2. Code 1 (bad key, quota, parse error) still fails immediately.
- **[Risk] Long retry delay hangs the UI** → Mitigation: `RetryAttempt` event carries the planned delay so the frontend can show a countdown. Max delay capped at 60 s.
- **[Risk] Stderr parsing is fragile if log format changes** → Mitigation: The `[pg:retry]` prefix is defined in a single constant in `retry.py`; tests assert the format.
- **[Risk] Default 3 retries × 60 s max = 3+ minute worst case** → Acceptable; user can lower `llm_retry_max` to 1 or 0 to disable.

## Migration Plan

1. Add `retry.py` with the retry decorator and `RetryPolicy` dataclass.
2. Wrap LLM provider calls in `generator.py` (generate step) and the plan generator with the decorator.
3. Add `--retry-max` / `--retry-delay` flags to `generate` and `plan` CLI commands; read `PLAYWRIGHT_GOD_RETRY_MAX` / `PLAYWRIGHT_GOD_RETRY_DELAY_S` as fallback env vars.
4. Add `RetryAttempt` to `PipelineEvent` in `pipeline.rs` and parse `[pg:retry]` lines in the stderr reader loop.
5. Add `llm_retry_max` / `llm_retry_delay_s` to `Settings` struct, `DEFAULT_SETTINGS`, and `validate()`.
6. Append retry flags to `plan` and `generate` step args in `build_step_execution`.
7. Add `RetryAttempt` handling in the frontend `usePipelineStore` (append a log annotation).
8. Add retry fields to the Settings UI.
9. Rollback: remove `--retry-max 0` or set `PLAYWRIGHT_GOD_RETRY_MAX=0` to disable; no data migration needed.

## Open Questions

- Should the `RetryAttempt` event appear inline in the step log pane or as a distinct banner? (Propose: inline annotation, `[Retry 2/3 — waiting 4 s…]`.)
- Should `llm_retry_max=0` mean "disabled" or "no limit"? (Propose: 0 = disabled, match common CLI convention.)
