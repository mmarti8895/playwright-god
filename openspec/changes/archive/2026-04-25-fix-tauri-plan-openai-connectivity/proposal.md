## Why

The desktop pipeline's plan phase intermittently fails to connect to OpenAI even when users believe `OPENAI_API_KEY`, provider, and model are configured. This blocks planning/generation workflows in the Tauri app and creates confusion because the same repository may work from CLI shells that load `.env` differently.

## What Changes

- Add explicit diagnostics for LLM connectivity before or at plan-step start, including clear failure reasons (missing key, provider/model mismatch, auth/permission errors, network/API errors).
- Standardize credential/config resolution for desktop subprocesses by defining deterministic precedence between saved desktop settings, secure-store values, and repository `.env` values.
- Ensure plan-phase subprocesses always receive the resolved `PLAYWRIGHT_GOD_PROVIDER`, `PLAYWRIGHT_GOD_MODEL`, and provider API key values.
- Improve UI messaging in Settings/Run output so users can tell which provider/model/key source is being used (without exposing secret values).
- Add tests covering OpenAI provider + `gpt-5.4` settings propagation and expected error surfacing.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `desktop-settings`: Clarify and enforce provider/model/API-key source resolution and preflight validation surfaced to users.
- `pipeline-orchestration`: Clarify plan-step environment injection, connectivity diagnostics, and failure classification for LLM-backed steps.

## Impact

- Affected code:
  - `desktop/src-tauri/src/settings.rs`
  - `desktop/src-tauri/src/pipeline.rs`
  - `desktop/src/lib/settings.ts`
  - `desktop/src/sections/Settings.tsx`
  - pipeline-related tests in `desktop/src/lib/` and `desktop/src-tauri/src/`
- Affected systems: Desktop settings persistence/secret resolution, subprocess orchestration, and run output UX.
- Dependencies: No new required external service; optional use of existing dotenv parsing in the desktop backend if repository `.env` fallback is enabled.