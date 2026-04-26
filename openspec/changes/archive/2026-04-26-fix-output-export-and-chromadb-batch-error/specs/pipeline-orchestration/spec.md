## ADDED Requirements

### Requirement: Index persistence respects ChromaDB max batch size
The index step SHALL split vector-store upserts into bounded batches so no single ChromaDB upsert exceeds the backend-reported max batch size.

#### Scenario: Oversized payload is split before upsert
- **WHEN** the index step prepares an upsert payload larger than the active ChromaDB max batch size
- **THEN** the payload is partitioned into multiple upserts and each issued upsert size is less than or equal to the max batch size

#### Scenario: Large repository index completes without batch-limit crash
- **WHEN** indexing a repository that would previously trigger `Batch size ... greater than max batch size ...`
- **THEN** the index step completes successfully without emitting an oversized-batch failure

### Requirement: Batch-limit resilience is covered by regression tests
The Python test suite SHALL include regression tests for oversized upsert payloads to prevent recurrence of ChromaDB batch-limit failures.

#### Scenario: Regression test reproduces pre-fix oversized case
- **WHEN** a test injects index data exceeding a representative max batch threshold
- **THEN** the test verifies the persistence layer performs multiple bounded upserts instead of one oversized call

#### Scenario: Regression test fails if bounded upsert protection is removed
- **WHEN** bounded upsert logic is bypassed or disabled
- **THEN** the regression test fails with an assertion indicating an oversized upsert attempt was made
