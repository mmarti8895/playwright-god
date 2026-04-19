## 1. Fix CLI test isolation regression

- [x] 1.1 Change `load_dotenv()` to `load_dotenv(override=False)` in `playwright_god/cli.py`
- [x] 1.2 Add an `autouse` fixture in `tests/unit/test_cli.py` that uses `monkeypatch.delenv(..., raising=False)` to clear `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `PLAYWRIGHT_GOD_PROVIDER`, `PLAYWRIGHT_GOD_MODEL`, and `OLLAMA_URL` for every test in the file
- [x] 1.3 Run `pytest tests/unit/test_cli.py -q` and confirm all 8 previously-failing tests now pass

## 2. Cover `crawler.py` lines 308–309 (OSError path)

- [x] 2.1 Add a unit test in `tests/unit/test_crawler.py` that creates a real file, makes it unreadable (`os.chmod(path, 0)`), runs `RepositoryCrawler().crawl(tmp_dir)`, and asserts the file is omitted from results without raising; restore mode in a `finally` block
- [x] 2.2 Add a fallback test path that monkeypatches `pathlib.Path.read_text` to raise `OSError` for the same assertion (covers root-user / Windows environments); skip the chmod test when `os.geteuid() == 0` if available

## 3. Cover `indexer.py` lines 69–70 (chromadb ImportError)

- [x] 3.1 Add a unit test in `tests/unit/test_indexer.py` that uses `monkeypatch.setitem(sys.modules, "chromadb", None)` (or `patch.dict(sys.modules, {"chromadb": None})`) and asserts `RepositoryIndexer()` raises `ImportError` with a message mentioning `pip install chromadb`

## 4. Cover `embedder.py` (DefaultEmbedder + OpenAIEmbedder)

- [x] 4.1 Add a test that asserts `DefaultEmbedder()` raises `ImportError` mentioning `pip install chromadb` when `chromadb.utils.embedding_functions` import fails (`patch.dict(sys.modules, {"chromadb.utils.embedding_functions": None})`)
- [x] 4.2 Add a happy-path test for `DefaultEmbedder()` that stubs `chromadb.utils.embedding_functions.DefaultEmbeddingFunction` with a `MagicMock` returning a deterministic 2D list, then calls the embedder and asserts the returned `list[list[float]]` matches
- [x] 4.3 Add a test that asserts `OpenAIEmbedder()` raises `ImportError` mentioning `pip install openai` when `import openai` fails (`patch.dict(sys.modules, {"openai": None})`)
- [x] 4.4 Add a test that constructs `OpenAIEmbedder()` with a stubbed `openai.OpenAI` (via `patch.dict(sys.modules, {"openai": MagicMock()})`) and verifies it reads `OPENAI_API_KEY` from `os.environ` when no explicit `api_key` is passed
- [x] 4.5 Add a test that calls `OpenAIEmbedder()(["a", "b"])` against a stubbed client whose `embeddings.create` returns objects with `.embedding` attributes; assert the embeddings list is returned in input order and the model name is forwarded

## 5. Verify and document

- [x] 5.1 Run `pytest tests/unit tests/integration --cov=playwright_god.crawler --cov=playwright_god.indexer --cov=playwright_god.embedder --cov-report=term-missing -q` and confirm all three modules report `100%` with no missing lines
- [x] 5.2 Run the full suite `pytest tests/unit tests/integration -q` and confirm 0 failures
- [x] 5.3 Update the "Current Coverage" table in `README.md` so `crawler.py`, `indexer.py`, and `embedder.py` all show `100%`; update the headline coverage figure if it changes
- [x] 5.4 Update the "verification date" line in the README to today's date
