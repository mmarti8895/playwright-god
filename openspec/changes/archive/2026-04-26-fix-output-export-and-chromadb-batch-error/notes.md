## Baseline Findings

### OUTPUT export baseline (before fix)
- OUTPUT pane Export used CSV export (`output.csv`) via `exportRows(...)` in `desktop/src/components/OutputPane.tsx`.
- Exported content was structured CSV (`timestamp,stream,line`) rather than plain OUTPUT pane text.
- Export operation result was not surfaced to users in-pane (no explicit success/failure log line).

### ChromaDB batch baseline (before fix)
- User-observed failure in index step:
  - `ValueError: Batch size of 18768 is greater than max batch size of 5461`
  - `FAIL index: step 'index' exited with code 1`
- Root cause: `RepositoryIndexer.add_chunks` performed one large `self._collection.upsert(...)` call with all chunks.

## Validation Evidence

### Desktop export tests
Command:
- `cd desktop && npm run test -- src/lib/wrappers.test.tsx`

Result:
- `1 passed` test file, `15 passed` tests.
- Includes new checks for:
  - `output_<DATETIME>.txt` filename contract
  - exact newline-preserving text write behavior
  - write-failure propagation

### Python indexer tests
Command:
- `c:/Users/mmart/projects/playwright-god/.venv/Scripts/python.exe -m pytest tests/unit/test_indexer.py -q`

Result:
- `20 passed` tests.
- Includes new regression checks for:
  - bounded upsert splitting under a deterministic small max-batch limit
  - fallback max-batch behavior when backend capabilities are unavailable
  - client-provided max-batch detection
