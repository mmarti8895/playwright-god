## Why

The `playwright_god` package targets ≥98% test coverage as a quality signal, but three core modules currently fall short of 100%: `crawler.py` (97%, 2 lines), `indexer.py` (97%, 2 lines), and `embedder.py` (65%, 16 lines). The uncovered branches are exactly the failure paths (unreadable files, missing optional dependencies, network embedding calls) that production users are most likely to hit, so they need test coverage before they bite.

Additionally, the recently-added `load_dotenv()` call in `cli.py` causes 8 CLI tests to fail when a developer's local `.env` contains a real `OPENAI_API_KEY` — coverage work must not require deleting your `.env`.

## What Changes

- Add unit tests covering the OS-error path in `RepositoryCrawler._read_file` (lines 308-309).
- Add unit tests covering the `chromadb` ImportError path in `RepositoryIndexer.__init__` (lines 69-70).
- Add unit tests covering `DefaultEmbedder` (success + ImportError) and `OpenAIEmbedder` (init, success, ImportError, missing-key) in `embedder.py` (lines 80-89, 92, 119-131, 134-135).
- **Fix test-isolation regression**: make `cli.py` `load_dotenv()` non-overriding of pre-existing env vars and ensure CLI test fixtures clear LLM-related env vars so tests are hermetic regardless of the developer's `.env`.
- Update README coverage table and notes to reflect the new 100% figures.

## Capabilities

### New Capabilities

*(none — this is a quality/test-coverage change with no new user-facing capability)*

### Modified Capabilities

*(none — no spec-level behavior changes; module public APIs are unchanged)*

## Impact

- **Code**: New test files under `tests/unit/` (`test_embedder.py` extended; possibly small additions to `test_crawler.py` and `test_indexer.py`). One small change to `playwright_god/cli.py` (`load_dotenv(override=False)`) and to `tests/unit/test_cli.py` fixtures.
- **APIs**: None changed. Public behavior of `RepositoryCrawler`, `RepositoryIndexer`, `DefaultEmbedder`, `OpenAIEmbedder` unchanged.
- **Dependencies**: None added. Tests use `unittest.mock` to stub out `chromadb` and `openai` import paths.
- **CI**: Coverage gate (if any) can be raised from 98% → 100% for these three modules.
- **Docs**: README "Current Coverage" section updated with new numbers.
