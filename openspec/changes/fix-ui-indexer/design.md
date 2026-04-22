## Context

The desktop application already has most of the backend pieces needed for UI-driven indexing: `desktop/src-tauri/src/lib.rs` exposes repository, pipeline, and artifact commands, and `desktop/src-tauri/src/artifacts.rs` can read memory maps and run RAG searches. The current UI layer does not complete that flow. `desktop/src/sections/Repository.tsx`, `MemoryMap.tsx`, `Rag.tsx`, and `Shell.tsx` import `@/lib/*` bridge modules that are absent from `desktop/src/`, so the frontend cannot reliably invoke the Tauri commands it depends on. At the same time, the user-facing "Run Index" affordances only redirect to the Generation section, while the backend only exposes a full pipeline run.

The change is cross-cutting because it touches the frontend command boundary, backend orchestration, and existing desktop capability contracts. The main constraint is to keep the desktop app as a thin shell over the existing CLI and artifact files. This change must not redesign the Python CLI or create a second source of truth for indexing behavior.

## Goals / Non-Goals

**Goals:**
- Restore the missing frontend bridge modules so the desktop shell can call repository, settings, pipeline, and artifact commands through one typed layer.
- Add a dedicated index-only run mode that invokes the existing CLI `index` step and reuses the current pipeline event model, cancellation, and output streaming.
- Expose a single shared "Run Index" action from the Repository, Memory Map, and RAG sections so index-backed views can recover without forcing the entire pipeline.
- Surface consistent index readiness states to the UI: no repository, index missing, index running, and index ready.
- Keep scope limited to the desktop app and its OpenSpec contracts.

**Non-Goals:**
- Changing `playwright_god.indexer` internals or adding new Python CLI subcommands.
- Reworking the full pipeline UX outside the minimum changes needed to support index-only runs.
- Introducing new persistence formats for memory maps, flow graphs, or search results.
- Bundling Python or changing desktop packaging behavior.

## Decisions

### 1. Restore a typed frontend bridge under `desktop/src/lib`

The frontend will regain a `desktop/src/lib/` layer that wraps Tauri `invoke` calls and shared client-side helpers for pipeline events, artifact reads, and repository commands.

Why:
- The current sections already depend on `@/lib/commands`, `@/lib/pipeline`, `@/lib/artifacts`, and adjacent helpers.
- Centralizing the desktop boundary keeps React components focused on UI state instead of command marshalling and error normalization.
- It provides a stable seam for Vitest mocks and coverage.

Alternative considered:
- Calling Tauri directly from each component. Rejected because it would duplicate command names, payload shaping, and error handling across the UI.

### 2. Extend the existing pipeline contract with a run mode instead of adding a second backend command family

`run_pipeline` will accept a run mode such as `full` or `index-only`, and the frontend bridge will expose helpers that map Repository/Memory Map/RAG CTAs onto the index-only mode.

Why:
- The backend already owns cancellation, output streaming, and run lifecycle events.
- Reusing the same registry and event schema avoids a parallel "index job" implementation that would drift from full-pipeline behavior.
- Index-only runs still produce artifacts that the existing viewers understand.

Alternative considered:
- Adding a dedicated `run_index` command beside `run_pipeline`. Rejected because it would duplicate process spawning, cancellation, and output handling for a subset of the same work.

### 3. Add an explicit index-status contract from Tauri to the frontend

The desktop backend will expose a small status payload describing whether the active repository has an index, whether a memory map is present, and whether an indexing run is currently active. The Repository, Memory Map, and RAG sections will derive their empty/loading/ready actions from that shared contract.

Why:
- The current UI mixes navigation state and artifact presence checks, which produces misleading CTAs.
- RAG readiness and memory-map readiness are related but not identical; a status contract makes those differences explicit instead of encoding them ad hoc in each section.
- A single status shape simplifies tests and prevents the viewers from probing the filesystem independently.

Alternative considered:
- Letting each component infer readiness by calling `read_memory_map` or trying a search and interpreting the error. Rejected because it couples user-visible behavior to side effects and produces inconsistent empty states.

### 4. Keep the fix desktop-local and spec-driven

The implementation will modify desktop specs and code only. Python CLI behavior is treated as an existing dependency, and any missing machine-readable CLI affordances remain follow-up work.

Why:
- The verified failures are in the desktop shell contract and its missing bridge code.
- Constraining the change avoids scope drift and preserves the repo’s “desktop is a thin shell over CLI artifacts” direction.

Alternative considered:
- Expanding the change to add new CLI subcommands or artifact formats. Rejected because the current bug can be fixed without broadening the public CLI surface.

## Risks / Trade-offs

- [Index status can be ambiguous when some artifacts exist but the chroma index is stale or missing] → Define status fields narrowly and have the UI show the specific missing prerequisite instead of a generic "indexed" badge.
- [Index-only orchestration may expose assumptions in progress UI that currently expect all pipeline steps] → Treat run mode as first-class state in the frontend bridge and progress store, with tests for full and index-only step lists.
- [Restoring the `desktop/src/lib` layer touches many imports at once] → Keep the bridge thin, typed, and covered by focused unit tests so most components only need wiring changes.
- [CTAs embedded in multiple viewers can drift] → Route all of them through one shared action helper instead of separate component-local implementations.

## Migration Plan

1. Add the missing frontend bridge modules and keep their APIs aligned with the imports already used by desktop sections where practical.
2. Extend the Tauri pipeline command and state contract to support index-only runs and index status reads.
3. Rewire Repository, Memory Map, and RAG to use the shared index action and status contract.
4. Add/update desktop tests, then verify the desktop suite and targeted Rust tests.
5. Update the README desktop workflow only if user-visible indexing behavior or steps change materially.

Rollback strategy: revert the desktop-only change set. No persisted data migration is required because artifact locations stay unchanged.

## Open Questions

- Which filesystem signals should define “index ready” for RAG: persisted chroma collection presence, memory map presence, or both? The implementation should settle this explicitly and test the chosen rule.
- Whether the Repository section should expose both "Run Index" and "Run Pipeline" as separate primary/secondary actions or collapse them behind one control. The spec for this change assumes both remain available.
