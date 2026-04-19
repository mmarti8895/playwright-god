## ADDED Requirements

### Requirement: Core modules SHALL achieve 100% line coverage

The `crawler.py`, `indexer.py`, and `embedder.py` modules in the `playwright_god` package SHALL have 100% line coverage as reported by `pytest --cov=playwright_god` over the `tests/unit` and `tests/integration` suites.

#### Scenario: Crawler handles unreadable files

- **WHEN** `RepositoryCrawler.crawl` encounters a file whose `read_text` raises `OSError` (permission denied, broken symlink, etc.)
- **THEN** the file is silently skipped (omitted from results) and the crawl continues without raising

#### Scenario: Indexer raises a clear error when chromadb is missing

- **WHEN** `RepositoryIndexer()` is instantiated in an environment where `import chromadb` fails
- **THEN** an `ImportError` is raised whose message instructs the user to `pip install chromadb`

#### Scenario: DefaultEmbedder raises a clear error when chromadb is missing

- **WHEN** `DefaultEmbedder()` is instantiated in an environment where `from chromadb.utils.embedding_functions import DefaultEmbeddingFunction` fails
- **THEN** an `ImportError` is raised whose message instructs the user to `pip install chromadb`

#### Scenario: DefaultEmbedder delegates to the chromadb embedding function

- **WHEN** `DefaultEmbedder()(["hello"])` is called with chromadb available
- **THEN** the call is forwarded to chromadb's `DefaultEmbeddingFunction` and the result is returned as a `list[list[float]]`

#### Scenario: OpenAIEmbedder raises a clear error when openai is missing

- **WHEN** `OpenAIEmbedder()` is instantiated in an environment where `import openai` fails
- **THEN** an `ImportError` is raised whose message instructs the user to `pip install openai`

#### Scenario: OpenAIEmbedder reads OPENAI_API_KEY from the environment

- **WHEN** `OpenAIEmbedder()` is instantiated with no explicit `api_key` and `OPENAI_API_KEY` is set
- **THEN** the underlying `openai.OpenAI` client is constructed with that key

#### Scenario: OpenAIEmbedder forwards calls to the embeddings API

- **WHEN** `OpenAIEmbedder()(["hello", "world"])` is called
- **THEN** the call is forwarded to `openai.embeddings.create(input=..., model=...)` and the embeddings list is returned in input order

### Requirement: CLI tests SHALL be hermetic with respect to the developer's `.env`

The `tests/unit/test_cli.py` suite SHALL pass deterministically regardless of values present in the developer's local `.env` file or shell environment for LLM-related variables.

#### Scenario: load_dotenv does not override existing shell env vars

- **WHEN** the `playwright_god.cli` module is imported with `OPENAI_API_KEY=sk-shell` already in `os.environ` and a `.env` file containing `OPENAI_API_KEY=sk-dotenv`
- **THEN** `os.environ["OPENAI_API_KEY"]` remains `"sk-shell"` after import (shell wins)

#### Scenario: CLI tests run with a clean LLM environment

- **WHEN** any test in `tests/unit/test_cli.py` executes
- **THEN** the variables `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `PLAYWRIGHT_GOD_PROVIDER`, `PLAYWRIGHT_GOD_MODEL`, and `OLLAMA_URL` are absent from `os.environ` unless the test sets them explicitly via `monkeypatch.setenv`
