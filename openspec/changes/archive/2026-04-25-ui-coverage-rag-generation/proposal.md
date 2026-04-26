## Why

The desktop app already exposes Coverage & Gaps, RAG Search, and Generation views, but they are not yet reliably usable as an end-to-end workflow for daily test authoring. We need these three UI paths to work predictably together so users can identify gaps, search code context, and launch generation without falling back to CLI-only flows.

## What Changes

- Wire Coverage & Gaps to load and render latest artifact data consistently, including robust empty/error states and stable sorting/export behavior.
- Make RAG Search reliably query the active repository index with clear index-ready, indexing, and missing-index states.
- Ensure Generation can be launched from both direct user input and Coverage-driven "generate for gap" actions with correct prompt handoff.
- Strengthen cross-section state transitions so moving between Coverage, RAG, and Generation preserves user intent and updates after runs.
- Add integration and section-level tests for these three workflows to prevent regressions.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `artifact-viewers`: Tighten requirements for Coverage & Gaps rendering, RAG result behavior, and coverage-to-generation handoff reliability.
- `pipeline-orchestration`: Clarify generation-triggered run behavior and post-run artifact refresh expectations used by these UI sections.

## Impact

- Affected code:
  - `desktop/src/sections/Coverage.tsx`
  - `desktop/src/sections/Rag.tsx`
  - `desktop/src/sections/Generation.tsx`
  - `desktop/src/lib/artifacts.ts`
  - `desktop/src/lib/pipeline-run.ts`
  - related state/tests under `desktop/src/state/` and `desktop/src/test/`
- Affected systems: Desktop Tauri shell + CLI subprocess orchestration and artifact readers.
- Dependencies: No new external runtime dependencies expected; test fixtures may need updates for coverage/index/generation scenarios.