## 1. Runtime Settings Resolution

- [x] 1.1 Implement resolved runtime settings loader in `desktop/src-tauri/src/settings.rs` with precedence: desktop settings/secrets, then repo `.env`, then process environment.
- [x] 1.2 Add source metadata for provider/model/key resolution (`settings`, `repo-dotenv`, `process-env`, `missing`) without exposing secret values.
- [x] 1.3 Add/extend Rust unit tests for precedence and source-metadata behavior, including OpenAI + `gpt-5.4` cases.

## 2. Pipeline Plan-Phase Diagnostics

- [x] 2.1 Update `desktop/src-tauri/src/pipeline.rs` to use resolved runtime settings for subprocess env injection in LLM-dependent steps.
- [x] 2.2 Add preflight diagnostics for `plan`/`generate` that fail fast on missing required OpenAI key and classify configuration errors.
- [x] 2.3 Add failure classification mapping for non-zero LLM step exits (auth/quota/network vs local missing-config) in run output events.
- [x] 2.4 Add/extend Rust tests for plan-step env propagation and diagnostics/failure classification.

## 3. Desktop UI Messaging

- [x] 3.1 Update frontend settings/output wiring (`desktop/src/lib/settings.ts`, `desktop/src/sections/Settings.tsx`, and related run-output paths) to surface effective provider/model/key source metadata safely.
- [x] 3.2 Ensure UI messages provide actionable guidance for missing key, provider mismatch, and upstream OpenAI/API errors without revealing secrets.
- [x] 3.3 Add or update frontend tests for settings/export messaging and diagnostic rendering.

## 4. Validation

- [x] 4.1 Run desktop frontend tests (`npm run test` in `desktop/`) and resolve regressions.
- [x] 4.2 Run tauri backend tests (`cargo test` in `desktop/src-tauri/`) and resolve regressions.
- [x] 4.3 Smoke-check the full pipeline path with provider=`openai`, model=`gpt-5.4`, and resolved `OPENAI_API_KEY` source to verify the plan phase no longer fails due to local config propagation.