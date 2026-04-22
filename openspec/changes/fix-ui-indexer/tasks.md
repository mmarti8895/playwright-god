## 1. Restore the desktop bridge layer

- [x] 1.1 Recreate the missing `desktop/src/lib/` modules required by the shell and desktop sections (`commands`, `pipeline`, `artifacts`, and any directly referenced support helpers) with typed wrappers around the existing Tauri commands
- [x] 1.2 Add or update Vitest coverage for the restored bridge APIs so command payloads, result shaping, and error normalization are exercised

## 2. Extend backend indexing orchestration

- [x] 2.1 Update `desktop/src-tauri/src/pipeline.rs` and the Tauri command surface to support a run mode that distinguishes full-pipeline runs from index-only runs while preserving cancellation and streamed output
- [x] 2.2 Add a backend index-status contract in `desktop/src-tauri/src/artifacts.rs` or adjacent desktop backend code that reports index readiness for the active repository
- [x] 2.3 Add or update Rust unit tests covering index-only run behavior, step lists, and index-status detection

## 3. Wire the shared Run Index UX

- [x] 3.1 Update `desktop/src/sections/Repository.tsx` to display index status and expose a dedicated `Run Index` action alongside the full pipeline workflow
- [x] 3.2 Update `desktop/src/sections/MemoryMap.tsx` so the empty-state CTA starts the shared index-only action and refreshes once indexing completes
- [x] 3.3 Update `desktop/src/sections/Rag.tsx` so the no-index state offers the same shared index-only action instead of only redirecting to another section
- [x] 3.4 Update the desktop pipeline/output state wiring so index-only runs report accurate progress, status, and artifact refresh behavior

## 4. Verify and document the change

- [x] 4.1 Add or update desktop UI tests for Repository, Memory Map, and RAG index CTA flows, including missing-index and active-indexing states
- [x] 4.2 Run the relevant desktop test suite (`npm test` in `desktop/` and targeted Rust tests) and confirm 100% coverage for newly changed desktop code paths
- [x] 4.3 Update `README.md` and any desktop workflow docs that describe how users start indexing from the UI
