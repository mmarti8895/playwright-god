# Test Suite

This directory contains the full test suite for **playwright-god** — unit tests for every core module, integration tests for the RAG pipeline, and Playwright-based E2E tests for a sample application.

---

## Roadmap
- [x] Playwright God core modules (chunker, crawler, embedder, generator, indexer)
- [x] Unit tests for all core modules
- [x] Integration tests for the full RAG pipeline (without LLM API calls)
- [x] A minimal sample app (HTML/CSS/JS) to test against
- [x] Playwright E2E tests with route interception to mock backend APIs
- [ ] CI integration (GitHub Actions)
- [ ] Test coverage reporting
- [ ] Additional E2E tests for messaging and invites/notifications (pending feature development)
- [ ] Load testing for the crawler and indexer (potential future addition)
- [ ] Accessibility testing (potential future addition)
- [ ] Performance benchmarks for embedding and generation (potential future addition)
- [ ] Visual regression testing for the sample app (potential future addition)
- [ ] Test data generation utilities for larger-scale integration tests (potential future addition)
- [ ] Mock LLM client for more realistic generation tests (potential future addition)
- [ ] Test fixtures for common file structures and content types (potential future addition)
- [ ] Test utilities for asserting relevance and similarity of search results (potential future addition)
- [ ] Documentation for how to write new tests and extend the suite (potential future addition)
- [ ] Regular maintenance to keep tests up-to-date with new features and changes (ongoing)
- [ ] Plugin and MCP support for test creation and management (potential future addition)

## Overview
- **Unit tests** (`tests/unit/`): Fast, isolated tests for each module (chunker, crawler, embedder, generator, indexer, CLI). No external dependencies or API keys required.
- **Integration tests** (`tests/integration/`): End-to-end tests for the full RAG pipeline (crawl → chunk → index → generate) using in-memory mocks. Still no external API calls.
- **E2E tests** (`tests/e2e/`): Playwright tests that run against a minimal sample app in `tests/fixtures/sample_app/`. They use route interception to mock backend APIs, so no real server or database is needed.  

## Directory Structure

```
tests/
├── conftest.py               # Shared fixtures (FileInfo, Chunk, in-memory indexer)
├── unit/                     # Fast, isolated module tests
│   ├── test_chunker.py       #   FileChunker – chunk sizes, overlap, IDs
│   ├── test_cli.py           #   CLI (Click) – index & generate subcommands
│   ├── test_crawler.py       #   RepositoryCrawler – walk, skip, language detection
│   ├── test_embedder.py      #   MockEmbedder – dimensions, determinism, norms
│   ├── test_generator.py     #   TemplateLLMClient & PlaywrightTestGenerator
│   └── test_indexer.py       #   RepositoryIndexer – add, search, clear (ChromaDB)
├── integration/
│   └── test_pipeline.py      # Full pipeline: crawl → chunk → index → generate
├── e2e/                      # Playwright browser tests against the sample app
│   ├── test_smoke_app.py     #   Landing page loads correctly
│   ├── test_auth_flow.py     #   Signup / signin with mocked API
│   ├── test_event_lifecycle.py #  Create and display events
│   ├── test_accessibility.py #   ARIA landmarks & semantic HTML
│   ├── test_responsive_layouts.py # Mobile / tablet / desktop viewports
│   ├── test_error_handling.py #   Friendly UI on backend 500 errors
│   ├── test_messaging.py     #   Messaging (skipped – feature pending)
│   └── test_invites_notifications.py # Invite flow (TODO – not yet implemented)
├── fixtures/
│   ├── conftest.py           # Auth & sample-data fixtures for E2E tests
│   ├── sample_data.py        # TEST_USER / TEST_EVENT constants
│   └── sample_app/           # Minimal todo app served during E2E runs
│       ├── index.html
│       ├── app.js
│       └── styles.css
└── helpers/
    └── page_models.py        # Page Object Models (LandingPage, LoginPage, EventsPage)
```

---

## Quick Start

### Prerequisites

- Python ≥ 3.11
- A virtual environment is recommended (the workspace already has `.venv/`)

### Install dependencies

```bash
pip install -e ".[dev]"
# For E2E tests only:
playwright install
```

### Run all tests

```bash
pytest                        # runs unit + integration + e2e
```

### Run a single tier

```bash
pytest tests/unit             # unit tests only (~118 tests)
pytest tests/integration      # integration pipeline tests (~8 tests)
pytest tests/e2e              # Playwright E2E tests (~8 tests)
```

### Run with coverage

```bash
pytest --cov=playwright_god --cov-report=term-missing
```

---

## Test Tiers

### Unit Tests (`tests/unit/`)

Fast, isolated tests for every core module. No network calls, no browser, no API keys required.

| Module | Tests | What's Covered |
|--------|------:|----------------|
| `test_chunker.py` | 24 | Chunk ID stability & uniqueness, overlap correctness, line coverage, metadata propagation, multi-file chunking |
| `test_cli.py` | 8 | `index` / `generate` subcommands, help output, error handling, file output, empty-index warnings |
| `test_crawler.py` | 32 | Directory walking, skip patterns (`.git`, `node_modules`, binaries), language detection (Python/JS/TS/HTML/CSS), max file-size limits, structure summaries |
| `test_embedder.py` | 11 | Embedding dimensions, deterministic output, unit-vector normalization, empty/long input edge cases |
| `test_generator.py` | 29 | URL extraction, CSS selector detection, form-field parsing, prompt construction, template-based generation |
| `test_indexer.py` | 14 | ChromaDB add/search/clear, search relevance scoring (0.0–1.0), metadata preservation, upsert idempotency |

### Integration Tests (`tests/integration/`)

Exercises the full RAG pipeline end-to-end **without** an LLM API key:

| Test | Description |
|------|-------------|
| `test_crawl_produces_files` | Verifies the crawler returns `FileInfo` objects from the sample app |
| `test_full_pipeline_indexes_chunks` | Crawl → chunk → index round-trip |
| `test_search_returns_relevant_result` | Indexed chunks are retrieved by semantic search |
| `test_generate_without_llm` | Generates a Playwright test file via `TemplateLLMClient` |
| `test_generate_includes_context_from_html` | Confirms HTML fixture content appears in retrieved context |
| `test_pipeline_idempotent_add` | Re-indexing the same chunks upserts without duplication |

### E2E Tests (`tests/e2e/`)

Browser-based tests driven by [Playwright for Python](https://playwright.dev/python/).
They run against the sample todo app in `tests/fixtures/sample_app/` and use **route interception** to mock backend APIs.

| Test | Description |
|------|-------------|
| `test_smoke_app.py` | Navigates to the landing page, asserts the heading is visible |
| `test_auth_flow.py` | Signs up and signs in via the `LoginPage` page model; mocks auth API |
| `test_event_lifecycle.py` | Creates an event and verifies it's displayed; routes POST & GET separately |
| `test_accessibility.py` | Checks ARIA landmarks (`main`, `banner`) are present |
| `test_responsive_layouts.py` | Resizes the viewport to **320×800** (mobile), **768×1024** (tablet), and **1280×800** (desktop) and makes assertions at each breakpoint |
| `test_error_handling.py` | Intercepts an API route to return HTTP 500 and verifies a friendly error message |
| `test_messaging.py` | Placeholder — gracefully skipped via `pytest.skip()` until the feature ships |
| `test_invites_notifications.py` | Placeholder — marked TODO |

---

## Key Fixtures

Defined in [tests/conftest.py](conftest.py) (shared) and [tests/fixtures/conftest.py](fixtures/conftest.py) (E2E-specific):

| Fixture | Scope | Description |
|---------|-------|-------------|
| `sample_repo_path` | function | Path to `tests/fixtures/sample_app/` |
| `simple_file_info` | function | A minimal `FileInfo` for a JS file |
| `simple_chunk` | function | A single `Chunk` derived from `simple_file_info` |
| `in_memory_indexer` | function | Ephemeral `RepositoryIndexer` backed by `MockEmbedder` — each test gets a unique ChromaDB collection |
| `signed_in_user` | function | Handles login (UI or API) for E2E tests |
| `sample_event_payload` | function | Dict with test event data |

---

## Page Object Models

Located in [tests/helpers/page_models.py](helpers/page_models.py). Each class wraps a Playwright `Page` and exposes high-level actions:

| Class | Purpose |
|-------|---------|
| `LandingPage` | Navigate and verify the landing page |
| `LoginPage` | Fill credentials and submit the login form |
| `EventsPage` | Create events through the UI |

---

## Patterns & Conventions

- **No external API dependencies** — `MockEmbedder` and `TemplateLLMClient` keep the entire test suite runnable offline.
- **Route interception** in E2E tests instead of running a real backend server.
- **Page Object Models** abstract selectors so tests read like user stories.
- **`data-testid` attributes** on UI elements provide stable selectors; prefer them over CSS classes or text selectors.
- **Unique ChromaDB collection names** (UUID-based) isolate each test so there's no state leakage.
- **Graceful skips** (`pytest.skip()`) for features that aren't implemented yet.

---

## Configuration

pytest options are set in [pyproject.toml](../pyproject.toml):

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --tb=short"
```

Coverage is configured to report on `playwright_god/` only:

```toml
[tool.coverage.run]
source = ["playwright_god"]
omit = ["tests/*"]

[tool.coverage.report]
show_missing = true
```

---

## Tips

- Update fixtures in `tests/fixtures/conftest.py` to match your app's auth and API endpoints.
- Add `data-testid` attributes to critical UI elements for stable selectors.
- Run a single test file with `pytest tests/unit/test_chunker.py`.
- Use `-k` to filter by test name: `pytest -k "test_search"`.
- Use `--headed` for Playwright tests to see the browser: `pytest tests/e2e --headed`.
