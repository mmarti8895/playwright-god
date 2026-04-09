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
# or install with support for a specific LLM provider
pip install -e ".[openai]"       # OpenAI (GPT-4o, etc.)
pip install -e ".[anthropic]"    # Anthropic Claude
pip install -e ".[gemini]"       # Google Gemini
pip install -e ".[ollama]"       # Ollama (local LLMs, requires requests)
pip install -e ".[all-llms]"     # All providers at once
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
| `--provider` | auto | LLM provider: `openai`, `anthropic`, `gemini`, `ollama`, `template` |
| `--model` | provider default | Model name (e.g. `gpt-4o`, `claude-3-5-sonnet-20241022`, `gemini-1.5-pro`, `llama3`) |
| `--api-key` | env var | API key (overrides the environment variable) |
| `--ollama-url` | `http://localhost:11434` | Ollama server URL (used only with `--provider=ollama`) |

### LLM backends

| Provider | How to select | Default model | Env var |
|----------|--------------|---------------|---------|
| OpenAI | `--provider openai` or `OPENAI_API_KEY` set | `gpt-4o` | `OPENAI_API_KEY` |
| Anthropic | `--provider anthropic` or `ANTHROPIC_API_KEY` set | `claude-3-5-sonnet-20241022` | `ANTHROPIC_API_KEY` |
| Google Gemini | `--provider gemini` or `GOOGLE_API_KEY` set | `gemini-1.5-pro` | `GOOGLE_API_KEY` |
| Ollama (local) | `--provider ollama` | `llama3` | *(none needed)* |
| Template | `--provider template` or no key found | *(offline)* | *(none needed)* |

Auto-detection order (when `--provider` is not specified): `OPENAI_API_KEY` → `ANTHROPIC_API_KEY` → `GOOGLE_API_KEY` → template fallback.

---

## Example

```bash
# Index the repository
playwright-god index . -d .idx

# Generate a test (offline template mode)
playwright-god generate "todo list: add, complete, and delete items" -d .idx -o tests/todo.spec.ts

# Generate with OpenAI
OPENAI_API_KEY=sk-... playwright-god generate "login page" -d .idx -o tests/login.spec.ts

# Generate with Anthropic Claude
ANTHROPIC_API_KEY=ant-... playwright-god generate "login page" -d .idx -o tests/login.spec.ts

# Generate with Google Gemini
GOOGLE_API_KEY=AIza... playwright-god generate "login page" -d .idx -o tests/login.spec.ts

# Generate with a local Ollama model
playwright-god generate "login page" -d .idx --provider ollama --model mistral -o tests/login.spec.ts
```

---

## Architecture

| Module | Responsibility |
|--------|---------------|
| `playwright_god/crawler.py` | Walk directory tree; build file-info objects and structure summary |
| `playwright_god/chunker.py` | Split `FileInfo` into overlapping `Chunk` objects |
| `playwright_god/embedder.py` | Embedding functions: `MockEmbedder` (tests), `DefaultEmbedder` (ChromaDB/ONNX), `OpenAIEmbedder` |
| `playwright_god/indexer.py` | ChromaDB-backed vector store: `add_chunks`, `search`, `clear` |
| `playwright_god/generator.py` | `TemplateLLMClient`, `OpenAIClient`, `AnthropicClient`, `GeminiClient`, `OllamaClient`, `PlaywrightTestGenerator` |
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
