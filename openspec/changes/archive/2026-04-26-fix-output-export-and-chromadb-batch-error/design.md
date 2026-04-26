## Context

The desktop app already shows live output for pipeline runs and exposes an Export action, but behavior is not formally constrained to produce a deterministic timestamped file with the exact pane contents. In parallel, indexing large repositories can fail in ChromaDB when a single upsert payload exceeds backend limits (`Batch size ... greater than max batch size ...`), which causes the `index` step to fail even when upstream crawling/chunking succeeded.

This change spans desktop UI/backend behavior and Python index persistence, so it requires coordinated requirements and implementation.

## Goals / Non-Goals

**Goals:**
- Guarantee OUTPUT export writes UTF-8 text files named `output_<DATETIME>.txt` with content parity to the visible OUTPUT pane at export time.
- Ensure index persistence never sends oversized Chroma upsert batches by splitting payloads into bounded chunks.
- Add deterministic tests for export behavior and large-batch ingestion resilience.
- Preserve existing user workflows and command surfaces (no new required flags for normal usage).

**Non-Goals:**
- Redesigning OUTPUT pane UI layout or adding new export formats (CSV/JSON).
- Replacing ChromaDB or changing embedding model/provider behavior.
- Optimizing all index performance bottlenecks beyond fixing batch-limit failures.

## Decisions

1. Define explicit OUTPUT export contract in `desktop-shell` specs and test both naming and content.
- Rationale: The feature exists but lacks strict acceptance criteria; formalizing behavior prevents regressions.
- Alternative considered: Treat export as best-effort with no strict naming/content guarantees. Rejected because troubleshooting requires predictable artifact handling.

2. Keep export naming format as `output_<DATETIME>.txt` with UTC-style sortable timestamp (existing timestamp utility semantics).
- Rationale: Human-readable and sortable; aligns with existing run-artifact timestamp patterns.
- Alternative considered: UUID filenames. Rejected because it is less user-friendly and harder to correlate chronologically.

3. Add a bounded upsert helper in index persistence path to chunk ids/embeddings/documents/metadatas using the effective max batch size.
- Rationale: Avoids backend-limit failures while preserving current data schema and retrieval behavior.
- Alternative considered: Catch exception and retry by halving recursively. Rejected as harder to reason about and test deterministically.

4. Compute safe chunk size from backend max when available, with conservative fallback when unavailable.
- Rationale: Keeps compatibility with Chroma variants while preventing oversized calls.
- Alternative considered: Hardcode one global constant. Rejected because backend max can vary by deployment/version.

5. Add regression tests that force oversized candidate payloads and verify multiple upserts occur and index completes.
- Rationale: The bug is a runtime integration failure; tests must prove prevention, not just unit logic.
- Alternative considered: Documentation-only workaround (smaller repos). Rejected as insufficient and user-hostile.

## Risks / Trade-offs

- [Risk] Chunked upserts increase number of write calls and may slightly increase index runtime.
  -> Mitigation: Use largest safe chunk size and keep chunking logic linear with minimal overhead.

- [Risk] Timestamp format mismatch between implementation and tests can cause brittle assertions.
  -> Mitigation: Centralize export filename formatting and assert with a regex contract in tests.

- [Risk] Partial success if one chunk fails mid-index could leave incomplete collections.
  -> Mitigation: Preserve existing failure semantics (non-zero exit) and clear error reporting; future work can add transactional cleanup if needed.

- [Risk] Differences between local Chroma and cloud/packaged variants may expose unknown max-batch behavior.
  -> Mitigation: Prefer runtime-detected limits and validate with integration-style tests against current pinned dependency.

## Migration Plan

1. Update spec deltas for `desktop-shell` and `pipeline-orchestration` in this change.
2. Implement OUTPUT export contract and tests in desktop frontend/backend test surfaces.
3. Implement chunked Chroma upsert in Python indexing path and add regression tests.
4. Run focused test suites for desktop export and Python indexing.
5. Rollout with no data migration required; rollback by reverting chunked helper and export contract changes if regressions are detected.

## Open Questions

- Should export include hidden/collapsed historical lines or only currently retained pane buffer lines when a line cap is active?
- Should chunked upsert emit progress metrics (chunk count/size) into logs for troubleshooting large repos?
- Do we want a user-configurable max batch size override for edge deployments, or keep this fully automatic?
