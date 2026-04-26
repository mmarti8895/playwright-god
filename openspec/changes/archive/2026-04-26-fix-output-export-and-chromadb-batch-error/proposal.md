## Why

The desktop workflow currently has two reliability gaps: exporting OUTPUT pane content is not guaranteed to produce a timestamped text artifact, and indexing can fail on large repositories with a ChromaDB batch-size overflow. These failures block users from preserving diagnostics and from completing the core index->analyze->generate loop.

## What Changes

- Add explicit OUTPUT export requirements so Export writes the visible OUTPUT pane content to `output_<DATETIME>.txt` and reports success/failure clearly.
- Add validation and integration tests for OUTPUT export naming, file contents, and behavior when output is empty or very large.
- Add index ingestion safeguards so embedding writes to ChromaDB are chunked under the engine max batch size instead of issuing oversized upserts.
- Add regression tests that reproduce the oversized-batch scenario and verify index completes successfully after chunked writes.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `desktop-shell`: Define and verify OUTPUT pane export behavior, including deterministic file naming and saved content expectations.
- `pipeline-orchestration`: Define resilience requirements for index-step persistence when vector-store max batch limits are exceeded by a single write payload.

## Impact

- Desktop frontend/backend export flow for OUTPUT pane artifacts.
- Indexing/embedding persistence path in Python modules that write vectors to ChromaDB.
- Automated coverage in desktop tests and Python unit/integration tests for large-batch indexing.
- User-facing reliability in troubleshooting and first-run indexing of large codebases.
