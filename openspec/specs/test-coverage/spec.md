# Test Coverage

## Purpose

Defines line-coverage and test-isolation guarantees for the `playwright_god` package. These requirements protect against regressions in defensive error paths (filesystem failures, missing optional dependencies) and against test-suite contamination from developer-local `.env` files.

## Requirements

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

### Requirement: Coverage & Gaps view supports run lifecycle states

The Coverage & Gaps view SHALL implement a four-state lifecycle: `idle` (no report, no active run), `running` (subprocess active), `done` (report loaded), and `error` (run failed or report unreadable). Visual affordances SHALL match the current state at all times.

#### Scenario: Idle state shows empty-state prompt with Run button

- **WHEN** no coverage report exists and no run is in progress
- **THEN** the view shows the "No coverage report yet" empty-state message AND an enabled **Run Coverage** button

#### Scenario: Running state shows progress log and Cancel button

- **WHEN** a coverage run is in progress
- **THEN** the view shows the live log panel, a **Cancel** button, and hides the run/clear buttons

#### Scenario: Done state shows report and Clear button

- **WHEN** a coverage run finishes successfully and the report is loaded
- **THEN** the view shows the full coverage report (totals header + tabs) and a **Clear** button in the toolbar

#### Scenario: Error state shows error message and Run button

- **WHEN** a coverage run exits with a non-zero code or the report file is unreadable
- **THEN** the view shows the error message from the log AND re-enables the **Run Coverage** button so the user can retry
