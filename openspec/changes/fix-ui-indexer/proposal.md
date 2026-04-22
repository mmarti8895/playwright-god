## Why

The desktop UI currently depends on repository indexing for the Memory Map and RAG views, but the user-facing indexing path is incomplete. The app exposes only a full-pipeline run, its "Run Index" call-to-actions only navigate to another tab instead of starting indexing, and the frontend bridge modules under `desktop/src/lib/` that should connect the UI to Tauri commands are missing from the worktree, leaving the repository/index flow unable to satisfy the existing desktop requirements.

## What Changes

- Restore the desktop frontend command bridge for repository selection, persisted UI state, pipeline events, artifact reads, and index-backed search so the app can invoke the Tauri backend instead of importing missing modules.
- Add an explicit desktop indexing workflow that can run the `index` step without forcing the rest of the pipeline, and surface index activity and failures in the existing output and progress UI.
- Update the Repository, Memory Map, and RAG sections to show consistent index readiness states and provide a one-click "Run Index" action that actually starts indexing for the active repository.
- Normalize artifact lookup and search behavior so index-dependent views can distinguish "repo not selected", "index missing", "index running", and "index ready" states.
- Add focused desktop tests for the restored bridge and the index CTA flows.

## Capabilities

### New Capabilities
<!-- None. -->

### Modified Capabilities
- `pipeline-orchestration`: The desktop app needs a dedicated index-only run mode in addition to the full pipeline so index-dependent views can trigger indexing directly.
- `artifact-viewers`: The Memory Map and RAG viewers need requirement-level changes so their empty states and recovery actions launch indexing instead of only redirecting the user.
- `desktop-shell`: The Repository section needs to surface index status and the primary index action as part of the core shell workflow.

## Impact

- **Affected frontend code**: `desktop/src/sections/Repository.tsx`, `desktop/src/sections/MemoryMap.tsx`, `desktop/src/sections/Rag.tsx`, `desktop/src/sections/Generation.tsx`, and the missing `desktop/src/lib/*` bridge modules that the shell and viewers already import.
- **Affected Tauri backend code**: `desktop/src-tauri/src/lib.rs`, `desktop/src-tauri/src/pipeline.rs`, and `desktop/src-tauri/src/artifacts.rs`.
- **Tests**: desktop Vitest coverage for the restored bridge and index-triggering UI behavior, plus Rust unit tests where pipeline/artifact contracts change.
- **Docs/specs**: desktop OpenSpec capability deltas for `pipeline-orchestration`, `artifact-viewers`, and `desktop-shell`. No Python CLI or public API changes are required.
