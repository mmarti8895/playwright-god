## Context

Three modules in `playwright_god/` have small uncovered regions. Each gap is a defensive branch that a unit test would not naturally exercise — they require either filesystem failure injection or stubbing optional dependencies (`chromadb`, `openai`).

Concrete uncovered lines (from `pytest --cov` on April 19, 2026):

| Module | Lines | What's there |
|---|---|---|
| `crawler.py` | 308–309 | `except OSError: return None` in `_read_file` |
| `indexer.py` | 69–70 | ImportError raise when `chromadb` is missing |
| `embedder.py` | 80–89 | `DefaultEmbedder.__init__` (success path requires real chromadb) |
| `embedder.py` | 92 | `DefaultEmbedder.__call__` |
| `embedder.py` | 119–131 | `OpenAIEmbedder.__init__` (ImportError + happy path) |
| `embedder.py` | 134–135 | `OpenAIEmbedder.__call__` |

Separately, the recently-added `from dotenv import load_dotenv; load_dotenv()` in `cli.py` reads the developer's real `.env` into `os.environ` at import time. Eight CLI tests in `tests/unit/test_cli.py` rely on `OPENAI_API_KEY` being absent and now fail locally for any developer who has put a real key in `.env`. This must be fixed in the same change to keep CI and local runs consistent.

## Goals / Non-Goals

**Goals:**

- Reach 100% line coverage for `crawler.py`, `indexer.py`, and `embedder.py`.
- Make `tests/unit/test_cli.py` hermetic: tests must pass regardless of what is in the developer's `.env`.
- No production behavior changes (apart from `load_dotenv(override=False)`, which is itself a safety improvement: shell env vars beat `.env`).

**Non-Goals:**

- Raising coverage on other modules (already at 100%).
- Refactoring the embedder/indexer/crawler APIs.
- Adding new test infrastructure (no `tox`, no `nox`, no new conftest patterns).
- Integration tests that require a real `chromadb` install via network.

## Decisions

### D1 — Use `unittest.mock` to stub optional imports

`embedder.py` and `indexer.py` lazily import `chromadb` / `openai` inside their constructors. To cover both the ImportError branch and the happy-path branch deterministically, tests will use `unittest.mock.patch.dict(sys.modules, ...)` to inject either `None` (triggers ImportError) or a `MagicMock()` (returns stubbed clients).

**Alternative considered:** real installs of `openai` in the test extras. Rejected — slows test runs and still doesn't cover the ImportError branch.

### D2 — Crawler OSError test uses a real unreadable path

For `_read_file`'s `except OSError`, the test will create a regular file then `chmod 000` it (with cleanup in a `finally`). On systems where `chmod` doesn't restrict reads (root, Windows), the test will fall back to monkeypatching `Path.read_text` to raise `OSError`. This keeps the test reliable across environments.

**Alternative considered:** only monkeypatching. Rejected — losing the chmod path costs us a real-world regression signal.

### D3 — Fix `load_dotenv` to be non-overriding + clear env in test fixtures

Two-part fix:

1. In `cli.py`, change `load_dotenv()` → `load_dotenv(override=False)`. This is the documented default but stating it explicitly makes intent obvious and ensures shell env vars (which CI uses) always win over a stale `.env`.
2. In `tests/unit/test_cli.py`, add an `autouse` fixture that monkeypatches `os.environ` to remove `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `PLAYWRIGHT_GOD_PROVIDER`, `PLAYWRIGHT_GOD_MODEL`, and `OLLAMA_URL` for each test. Individual tests that need a key set it explicitly via `monkeypatch.setenv`.

**Alternative considered:** skip `load_dotenv` entirely when `pytest` is detected. Rejected — fragile, magic, and wrong layer; the test fixture is the right place.

### D4 — No new test files

Reuse the existing `tests/unit/test_crawler.py`, `tests/unit/test_indexer.py`, `tests/unit/test_embedder.py`. Keeps test discovery uncluttered.

## Risks / Trade-offs

- **Risk:** mocking `sys.modules['chromadb'] = None` could leak into other tests in the same process. → **Mitigation:** use `patch.dict(sys.modules, ..., clear=False)` as a context manager so the patch is reverted at test exit.
- **Risk:** `chmod 000` test fails when run as root (e.g., in some CI containers). → **Mitigation:** detect `os.geteuid() == 0` and skip-to-monkeypatch fallback.
- **Risk:** the autouse env-clearing fixture hides bugs where production code legitimately reads those vars. → **Mitigation:** scope the fixture to `tests/unit/test_cli.py` only; integration tests keep their existing setup.
- **Trade-off:** mocked embedder tests don't exercise the real `all-MiniLM-L6-v2` ONNX model path. That's acceptable — model correctness is upstream's responsibility, we're only testing our wrapper.
