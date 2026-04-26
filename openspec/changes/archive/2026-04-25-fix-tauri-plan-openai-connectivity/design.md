## Context

The Tauri desktop app runs pipeline steps by spawning `playwright-god` subprocesses and injecting environment variables from desktop settings + secure-store lookups. In practice, users report plan-phase OpenAI failures despite setting provider/model/API key, especially when they also rely on repository `.env` workflows in terminal usage.

Current behavior makes it hard to distinguish whether failures are caused by missing credential propagation, stale provider/model configuration, or true upstream OpenAI/network errors. The result is repeated failed runs with weak guidance.

## Goals / Non-Goals

**Goals:**
- Define deterministic runtime resolution for provider/model/API keys used by desktop-spawned subprocesses.
- Ensure plan-phase subprocesses receive the resolved OpenAI configuration when provider=`openai` and model like `gpt-5.4` is selected.
- Add structured diagnostics that classify connectivity/config/auth failures for plan/generate steps.
- Surface safe, actionable UX in Settings and run output without exposing secret values.
- Add regression tests for env propagation and failure classification.

**Non-Goals:**
- Building a new remote connectivity service.
- Logging or displaying raw secrets.
- Replacing existing provider abstraction in CLI.

## Decisions

### Decision: Deterministic settings resolution order
Resolve runtime values in this order:
1. Explicit desktop settings + secure-store secrets
2. Repository `.env` fallback (only if corresponding value is unset in desktop settings/secrets)
3. Process environment fallback

Alternatives considered:
- Process env first. Rejected because desktop users expect saved settings to be authoritative.
- `.env` only. Rejected because settings UI and secure-store integration would be bypassed.

### Decision: Add plan-step preflight diagnostics
Before executing LLM-dependent steps, emit a short classified diagnostic envelope (provider/model present, key source present/absent, repo path, step name). If key is absent or provider/model invalid, fail fast with a structured message.

Alternatives considered:
- Only rely on subprocess stderr. Rejected because messages are often ambiguous and provider-specific.

### Decision: Keep secrets masked end-to-end
Never include key contents in events/log lines. Emit only source metadata (`settings`, `repo-dotenv`, `process-env`, `missing`).

Alternatives considered:
- Include partial key prefix for debugging. Rejected due to unnecessary risk.

## Risks / Trade-offs

- [Risk] Additional `.env` parsing may cause source-of-truth confusion. -> Mitigation: explicit precedence documentation + run output metadata.
- [Risk] Diagnostic checks may duplicate CLI validation. -> Mitigation: keep checks shallow (presence/shape) and defer provider-specific verification to CLI/API responses.
- [Risk] Existing users relying on implicit process env precedence may see changed behavior. -> Mitigation: document precedence and add migration note in Settings UI/help text.

## Migration Plan

1. Implement resolved-settings loader in desktop backend with precedence + source metadata.
2. Update pipeline run setup to use resolved settings and emit diagnostics for plan/generate.
3. Update frontend settings/output messaging to display effective provider/model/key source safely.
4. Add unit tests for precedence matrix and pipeline diagnostics.
5. Validate with desktop test suite and targeted tauri Rust tests.

Rollback strategy:
- Revert precedence changes to existing settings/process-env logic while keeping secret masking protections.

## Open Questions

- Should repository `.env` fallback be always-on or controlled by a Settings toggle?
- Should diagnostics be emitted for all pipeline steps or only LLM-dependent steps (`plan`, `generate`)?