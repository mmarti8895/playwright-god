## 1. Scope and test baselines

- [x] 1.1 Reproduce current OUTPUT export behavior in desktop tests (naming/content/failure) and document failing baseline assertions.
- [x] 1.2 Reproduce the ChromaDB oversized batch failure path in Python tests using a deterministic oversized payload fixture.

## 2. OUTPUT export contract implementation

- [x] 2.1 Update desktop output export logic to always write UTF-8 `output_<DATETIME>.txt` snapshots from the current OUTPUT pane buffer.
- [x] 2.2 Ensure export success/failure is surfaced clearly in the UI (success confirmation, explicit error message on write failure).
- [x] 2.3 Centralize timestamped output filename formatting so runtime behavior and tests share one contract.

## 3. OUTPUT export verification

- [x] 3.1 Add/extend desktop tests to assert filename pattern compliance for exported OUTPUT files.
- [x] 3.2 Add/extend desktop tests to assert exact content parity (including line breaks) between pane buffer and saved file.
- [x] 3.3 Add/extend desktop tests to assert failure-path messaging when file writes fail.

## 4. ChromaDB batch-limit resilience implementation

- [x] 4.1 Add a bounded upsert helper in index persistence that chunks ids/embeddings/documents/metadatas to the effective max batch size.
- [x] 4.2 Resolve effective max batch size from backend capabilities when available, with a conservative fallback when unavailable.
- [x] 4.3 Wire chunked upsert logic into the index step so oversized single-call upserts are never issued.

## 5. ChromaDB regression coverage and validation

- [x] 5.1 Add Python regression tests proving oversized candidate payloads are split into multiple safe upserts.
- [x] 5.2 Add/extend tests proving indexing completes for repositories that previously triggered `Batch size ... greater than max batch size ...`.
- [x] 5.3 Run focused desktop and Python test suites for export and indexing paths, then record pass/fail evidence in the change notes.
