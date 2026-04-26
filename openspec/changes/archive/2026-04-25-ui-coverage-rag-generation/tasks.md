## 1. Coverage & Gaps Reliability

- [x] 1.1 Update `desktop/src/sections/Coverage.tsx` to reset stale report state on repository changes and render deterministic loading/empty/content branches.
- [x] 1.2 Ensure file sorting defaults to least-covered-first for coverage rows and preserve explicit user sort toggles.
- [x] 1.3 Verify `Generate test` actions for uncovered routes/files set `generationPrompt` and navigate to Generation with one-time prompt consumption.
- [x] 1.4 Confirm CSV export output for files/routes remains stable for rendered rows and add assertions where tests exist.

## 2. RAG Search Reliability

- [x] 2.1 Update `desktop/src/sections/Rag.tsx` to normalize index status lifecycle (checking, missing-index, indexing, ready) per active repository.
- [x] 2.2 Ensure search execution is guarded by index-ready state and returns deterministic UI states for loading, no results, and command errors.
- [x] 2.3 Wire the RAG "Run Index" CTA to the existing index-only run path and refresh readiness via artifact version updates.

## 3. Generation + Orchestration Integration

- [x] 3.1 Validate `desktop/src/sections/Generation.tsx` consume-and-clear behavior for cross-section prompt handoff.
- [x] 3.2 Ensure generation description text is passed through `runManagedPipeline` invocation and reflected in run status/progress controls.
- [x] 3.3 Verify post-run artifact refresh signaling so Coverage and RAG views observe latest artifacts after successful runs.

## 4. Test Coverage for UI Workflow

- [x] 4.1 Add or update section tests for Coverage empty-state, rendered rows, and generate-for-gap handoff behavior.
- [x] 4.2 Add or update section tests for RAG missing-index, index-ready search, and index-only CTA flows.
- [x] 4.3 Add or update Generation/pipeline tests for prompt prefill consumption, run initiation, and cancellation/status transitions.
- [x] 4.4 Run `make desktop-test` (or equivalent vitest + cargo commands) and resolve regressions introduced by this change.