## 1. Python retry infrastructure

- [x] 1.1 Create `playwright_god/retry.py` with `RetryPolicy` dataclass (`max_attempts: int`, `initial_delay_s: float`) and `with_retry(policy, fn, is_transient)` function implementing exponential backoff with full jitter capped at 60 s
- [x] 1.2 Add `RETRY_PREFIX = "[pg:retry]"` constant to `retry.py` and emit `[pg:retry] attempt=N/M delay=S` and `[pg:retry] exhausted attempts=N` lines to stderr at the correct points
- [x] 1.3 Add unit tests in `tests/unit/test_retry.py` covering: success on first attempt, success after one retry, exhausted retries, non-transient error bypasses retry, delay is capped at 60 s, jitter is non-negative

## 2. CLI integration

- [x] 2.1 Add `--retry-max` (int, default reads `PLAYWRIGHT_GOD_RETRY_MAX` env var, fallback 3) and `--retry-delay` (float, default reads `PLAYWRIGHT_GOD_RETRY_DELAY_S` env var, fallback 2.0) Click options to the `plan` command in `cli.py`
- [x] 2.2 Add the same `--retry-max` and `--retry-delay` Click options to the `generate` command in `cli.py`
- [x] 2.3 Wrap the LLM provider call in `generator.py` with `with_retry` using a `RetryPolicy` built from the CLI options; treat exit-code-2 / `upstream-network` exceptions as transient
- [x] 2.4 Wrap the LLM call in the plan generator (wherever `generate_plan` calls the provider) with `with_retry` using the same policy
- [x] 2.5 Add CLI integration tests asserting `--retry-max 0` disables retries and `--retry-max 2` retries twice before failing

## 3. Tauri settings extension

- [x] 3.1 Add `llm_retry_max: u32` (default 3) and `llm_retry_delay_s: f64` (default 2.0) fields to the `Settings` struct in `settings.rs`; update `Default` impl and `validate()` (clamp min to 0 / 0.0)
- [x] 3.2 Update the `settings_round_trip_through_serde_json` test in `settings.rs` to include the new fields
- [x] 3.3 Add unit test asserting negative-equivalent edge cases are clamped (i.e., `validate()` sets negative delay to 0.0 if applicable)

## 4. Tauri pipeline integration

- [x] 4.1 Add `RetryAttempt { step: String, attempt: u32, max: u32, delay_s: f64 }` variant to the `PipelineEvent` enum in `pipeline.rs`
- [x] 4.2 In the stderr-reading loop of `build_step_execution`, parse `[pg:retry] attempt=N/M delay=S` lines and emit both a `RetryAttempt` event and the raw `StderrLine` event
- [x] 4.3 Append `--retry-max <n>` and `--retry-delay <s>` to the subprocess args for `plan` and `generate` steps in `build_step_execution`, reading values from `settings`
- [x] 4.4 Add a Rust unit test asserting that `plan` and `generate` args contain the retry flags, and that non-retryable steps (e.g., `index`) do not

## 5. Frontend settings

- [x] 5.1 Add `llm_retry_max: number` and `llm_retry_delay_s: number` to the `Settings` interface in `desktop/src/lib/settings.ts`; set defaults `llm_retry_max: 3, llm_retry_delay_s: 2.0` in `DEFAULT_SETTINGS`
- [x] 5.2 Add "Max LLM retries" and "Retry initial delay (s)" `<Field>` inputs with hint text in `Settings.tsx`, with inline validation that rejects values below 0
- [x] 5.3 Add a vitest test asserting default values are present and that the Settings form renders both new fields

## 6. Frontend pipeline state

- [x] 6.1 Add `retryAttempt` to the pipeline event union type in `desktop/src/lib/pipeline.ts` (or wherever `PipelineEvent` is typed)
- [x] 6.2 In `usePipelineStore`, handle `RetryAttempt` events by setting `retrying: true`; clear on `finished`, `failed`, `cancelled`
- [x] 6.3 Add a vitest test asserting `RetryAttempt` event sets `retrying=true` and that subsequent `finished`/`failed` events clear it

## 7. Documentation and integration validation

- [x] 7.1 Update `README.md` to document `--retry-max` / `--retry-delay` flags and the env var fallbacks
- [ ] 7.2 Run the full unit suite (`pytest tests/unit/ -q`) and confirm all tests pass
- [x] 7.3 Run `npm run test` in `desktop/` and confirm all vitest tests pass
- [x] 7.4 Run `cargo check` in `desktop/src-tauri/` and confirm zero errors
