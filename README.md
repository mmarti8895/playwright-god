# playwright-god

**playwright-god** is a CLI tool that remembers your repository's code structure and context via a **RAG (Retrieval-Augmented Generation)** pipeline, then uses that context to generate high-quality [Playwright](https://playwright.dev/) tests.

---

## How it works

```
Repository files
      │
      ▼
 RepositoryCrawler          ← walks the directory tree, reads file contents
      │
      ▼
    FileChunker              ← splits files into overlapping line-based chunks
      │
      ▼
  RepositoryIndexer          ← embeds chunks & stores them in a ChromaDB vector store
      │
      ▼  (at query time)
   RAG search                ← retrieves the most relevant chunks for a given description
      │
      ▼
PlaywrightTestGenerator      ← builds a prompt from the retrieved context and calls an LLM
      │
      ▼
  Playwright .spec.ts        ← generated TypeScript test file
```

---

## Installation

```bash
pip install -e .
# or install with optional OpenAI support
pip install -e ".[openai]"
```

---

## Quick start

### 1. Index a repository

```bash
playwright-god index /path/to/your/repo
```

This crawls the repository, chunks every source file, embeds the chunks, and saves a [ChromaDB](https://www.trychroma.com/) vector store to `.playwright_god_index/`.

Options:

| Flag | Default | Description |
|------|---------|-------------|
| `-d`, `--persist-dir` | `.playwright_god_index` | Directory to save the index |
| `-c`, `--collection` | `repo` | ChromaDB collection name |
| `--chunk-size` | `80` | Lines per chunk |
| `--overlap` | `10` | Overlapping lines between chunks |

### 2. Generate a Playwright test

```bash
playwright-god generate "user login flow on the /login page"
```

Retrieves relevant context from the index and generates a TypeScript Playwright test on **stdout**.

Options:

| Flag | Default | Description |
|------|---------|-------------|
| `-d`, `--persist-dir` | `.playwright_god_index` | Directory with the persisted index |
| `-c`, `--collection` | `repo` | ChromaDB collection name |
| `-o`, `--output` | stdout | Write test to this file |
| `--n-context` | `10` | Number of context chunks to retrieve |
| `--model` | `gpt-4o` | OpenAI model (used when `OPENAI_API_KEY` is set) |

### LLM backends

| Condition | Backend used |
|-----------|-------------|
| `OPENAI_API_KEY` env var is set | `OpenAIClient` (calls OpenAI Chat Completions API) |
| No API key | `TemplateLLMClient` (offline template generator, no API call) |

---

## Example

```bash
# Index the repository
playwright-god index . -d .idx

# Generate a test (offline template mode)
playwright-god generate "todo list: add, complete, and delete items" -d .idx -o tests/todo.spec.ts

# Generate with OpenAI
OPENAI_API_KEY=sk-... playwright-god generate "login page" -d .idx -o tests/login.spec.ts
```

---

## Architecture

| Module | Responsibility |
|--------|---------------|
| `playwright_god/crawler.py` | Walk directory tree; build file-info objects and structure summary |
| `playwright_god/chunker.py` | Split `FileInfo` into overlapping `Chunk` objects |
| `playwright_god/embedder.py` | Embedding functions: `MockEmbedder` (tests), `DefaultEmbedder` (ChromaDB/ONNX), `OpenAIEmbedder` |
| `playwright_god/indexer.py` | ChromaDB-backed vector store: `add_chunks`, `search`, `clear` |
| `playwright_god/generator.py` | `TemplateLLMClient`, `OpenAIClient`, `PlaywrightTestGenerator` |
| `playwright_god/cli.py` | Click CLI (`index` and `generate` commands) |

---

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run all tests
pytest

# Run with coverage
pytest --cov=playwright_god --cov-report=term-missing
```

### Test structure

```
tests/
  conftest.py                 # shared fixtures (sample app, in-memory indexer)
  fixtures/
    sample_app/               # small HTML/JS/CSS app used in integration tests
  unit/
    test_crawler.py
    test_chunker.py
    test_embedder.py
    test_indexer.py
    test_generator.py
    test_cli.py
  integration/
    test_pipeline.py          # full crawl → index → generate pipeline
```

---

## License

MIT
