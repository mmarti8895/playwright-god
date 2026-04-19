# playwright-god

`playwright-god` is a CLI that indexes a repository, builds a compact memory of how its files relate, and uses that context to generate Playwright tests and plans from repository-aware RAG context.

## What It Does Now

- It is a Python CLI that analyzes a repository and builds retrieval context for AI-assisted test authoring.
- `index` crawls files with `RepositoryCrawler`, splits them into overlapping chunks with `FileChunker`, embeds them into Chroma with `RepositoryIndexer`, and can save a compact `MemoryMap`.
- During indexing it also infers higher-level feature structure via `feature_map.py`, so the memory map is not just file inventory; it also carries inferred features, correlations, and test opportunities.
- `generate` performs RAG search over the indexed chunks, optionally injects the saved memory map plus auth/logging hints, and asks an LLM to produce a TypeScript Playwright spec for `@playwright/test`.
- `plan` uses the memory map or index inventory to produce a Markdown test plan grouped around feature areas.
- There is also an offline template fallback, so generation and planning still work without an external LLM API key.

## How It Works

```text
Repository files
      │
      ▼
 RepositoryCrawler          ← walks the directory tree, reads file contents
      │
      ▼
    FileChunker             ← splits files into overlapping line-based chunks
      │
      ▼
 RepositoryIndexer          ← embeds chunks & stores them in a ChromaDB vector store
      │
      ├─► MemoryMap          ← optional JSON snapshot of every indexed file & chunk
      │                         (saved with `index --memory-map`, used by `generate`
      │                          and `plan` to give the AI a full codebase overview)
      │
      ▼  (at query time)
   RAG search               ← retrieves the most relevant chunks for a given description
      │
      ▼
PlaywrightTestGenerator     ← builds a prompt from the retrieved context and calls an LLM
      │
      ├─► generate           ← produces a TypeScript Playwright `.spec.ts` file
      └─► plan               ← produces a Markdown test-plan document
```

During indexing, the tool infers feature areas, shared artifacts, and candidate test opportunities. When you save a memory map, that higher-level repository understanding can be reused later without rebuilding the full analysis.

## Installation

```bash
pip install -e .
pip install -e ".[dev]"
```

Optional provider extras:

```bash
pip install -e ".[openai]"
pip install -e ".[anthropic]"
pip install -e ".[gemini]"
pip install -e ".[ollama]"
pip install -e ".[all-llms]"
```

## Quick Start

Index a repository and save reusable memory:

```bash
playwright-god index . -d .idx --memory-map .idx/memory_map.json
```

Expected output includes:

- crawl and chunk progress
- a feature summary with evidence-backed areas such as authentication or navigation
- a persisted vector index
- a saved memory map when `--memory-map` is provided

Generate a TypeScript Playwright spec:

```bash
playwright-god generate "user login flow" -d .idx --memory-map .idx/memory_map.json -o tests/login.spec.ts
```

Create a feature-oriented test plan:

```bash
playwright-god plan --memory-map .idx/memory_map.json -o inferred_test_plan.md
```

Options:

| Flag | Default | Description |
|------|---------|-------------|
| `-m`, `--memory-map` | *(build from index)* | Path to the memory map JSON file |
| `-d`, `--persist-dir` | `.playwright_god_index` | Fallback index directory when no `--memory-map` |
| `-c`, `--collection` | `repo` | ChromaDB collection name (fallback only) |
| `--focus` | *(none)* | Free-text hint to narrow the plan (e.g. `"checkout flow"`) |
| `-o`, `--output` | stdout | Write the plan to this file (must be a file path, not a directory) |
| `--provider` | auto | LLM provider |
| `--model` | provider default | Model name |

### Generate a Playwright test
Focus the plan on one area:

```bash
playwright-god plan --memory-map .idx/memory_map.json --focus "authentication" -o auth_plan.md
```

## CLI Notes

`index`
- crawls files
- chunks source content
- infers feature groupings and correlations
- persists embeddings
- optionally saves a compact memory map

`generate`
- retrieves relevant repository chunks through RAG search
- injects optional saved memory and auth context
- emits TypeScript Playwright tests for `@playwright/test`

| Flag | Default | Description |
|------|---------|-------------|
| `-d`, `--persist-dir` | `.playwright_god_index` | Directory with the persisted index |
| `-c`, `--collection` | `repo` | ChromaDB collection name |
| `-o`, `--output` | stdout | Write test to this file (must be a file path, not a directory) |
| `--n-context` | `10` | Number of context chunks to retrieve |
| `-m`, `--memory-map` | *(none)* | Inject memory map context into the prompt |
| `--provider` | auto | LLM provider: `openai`, `anthropic`, `gemini`, `ollama`, `template` |
| `--model` | provider default | Model name (e.g. `gpt-4o`, `claude-3-5-sonnet-20241022`, `gemini-1.5-pro`, `llama3`) |
| `--api-key` | env var | API key (overrides the environment variable) |
| `--ollama-url` | `http://localhost:11434` | Ollama server URL (used only with `--provider=ollama`) |
`plan`
- turns a saved memory map or index inventory into a Markdown test plan
- groups scenarios by inferred feature area when that metadata is available

## Memory Map

The saved memory map keeps the original file inventory and extends it with streamlined repository understanding:

```json
{
  "generated_at": "2026-04-11T00:00:00+00:00",
  "total_files": 12,
  "total_chunks": 87,
  "languages": { "python": 6, "javascript": 4, "html": 2 },
  "files": [],
  "schema_version": "2.0",
  "features": [],
  "correlations": [],
  "test_opportunities": [],
  "source_root": "/abs/path/to/repo"
}
```

This format is meant to stay compact: it keeps file/chunk inventory plus evidence references, not full chunk text.

## Providers

### Configuration via `.env` File

Copy `example.env` to `.env` and configure your LLM provider:

```bash
cp example.env .env
```

> ⚠️ **Never commit `.env`.** It is already listed in `.gitignore`. The repo also ships
> a `gitleaks` pre-commit hook and CI scan to block accidental key commits — see
> [Secret Hygiene](#secret-hygiene) below.

Edit `.env` to set your preferred provider and API key:

```bash
# Select your provider
PLAYWRIGHT_GOD_PROVIDER=openai

# Optionally override the default model
PLAYWRIGHT_GOD_MODEL=gpt-4o

# Set your API key
OPENAI_API_KEY=sk-...
```

### Configuration Priority

Settings are resolved in this order (highest priority first):

1. **CLI arguments** (`--provider`, `--model`, `--api-key`, `--ollama-url`)
2. **`.env` file** (`PLAYWRIGHT_GOD_PROVIDER`, `PLAYWRIGHT_GOD_MODEL`, `OLLAMA_URL`)
3. **Environment variables** (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`)
4. **Fallback** to offline `template` generator

### Environment Variables

| Variable | Description |
|----------|-------------|
| `PLAYWRIGHT_GOD_PROVIDER` | LLM provider: `openai`, `anthropic`, `gemini`, `ollama`, `template` |
| `PLAYWRIGHT_GOD_MODEL` | Model name (overrides provider default) |
| `OPENAI_API_KEY` | OpenAI API key |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `GOOGLE_API_KEY` | Google AI (Gemini) API key |
| `OLLAMA_URL` | Ollama server URL (default: `http://localhost:11434`) |

### Auto-detection

When `--provider` is omitted and `PLAYWRIGHT_GOD_PROVIDER` is not set, the CLI auto-detects based on available API keys:

1. `OPENAI_API_KEY` → `openai`
2. `ANTHROPIC_API_KEY` → `anthropic`
3. `GOOGLE_API_KEY` → `gemini`
4. Fallback → offline `template` generator

### Supported Providers

- `openai` (default model: `gpt-4o`)
- `anthropic` (default model: `claude-3-5-sonnet-20241022`)
- `gemini` (default model: `gemini-1.5-pro`)
- `ollama` (default model: `llama3`)
- `template` (offline fallback)

## Development

Install dev dependencies:

```bash
pip install -e ".[dev]"
```

Run targeted tests:

```bash
pytest tests/unit/test_feature_map.py tests/unit/test_memory_map.py tests/unit/test_generator.py tests/unit/test_cli.py -q
pytest tests/integration/test_pipeline.py tests/integration/test_feature_memory_pipeline.py tests/integration/test_self.py -q
pytest tests/integration/test_auth_pipeline.py tests/integration/test_logging_pipeline.py -q
```

Run coverage:

```bash
pytest --cov=playwright_god --cov-report=term-missing
```

## Current Coverage

Most recent verification in this workspace on April 19, 2026:

- `tests/unit` + `tests/integration`: `312 passed`
- package coverage for `playwright_god`: `99%` (`1052` statements, `2` missed)

Per-module coverage from that run:

| Module | Coverage |
|------|---------|
| `playwright_god/__init__.py` | `100%` |
| `playwright_god/auth_templates.py` | `100%` |
| `playwright_god/chunker.py` | `100%` |
| `playwright_god/cli.py` | `99%` |
| `playwright_god/crawler.py` | `100%` |
| `playwright_god/embedder.py` | `100%` |
| `playwright_god/feature_map.py` | `100%` |
| `playwright_god/generator.py` | `100%` |
| `playwright_god/indexer.py` | `100%` |
| `playwright_god/memory_map.py` | `100%` |

Notes:

- The browser-backed `tests/e2e` suite does not currently pass in this sandboxed environment.
- After installing Playwright Chromium, the e2e run still failed during browser launch with a Linux sandbox error from Chromium (`sandbox_host_linux.cc`, `Operation not permitted`).
- The Python/package coverage figure above comes from the passing unit + integration run, which exercises the repository-analysis and generation pipeline end to end.

## Repository Layout

```text
playwright_god/
  cli.py
  crawler.py
  chunker.py
  feature_map.py
  generator.py
  indexer.py
  memory_map.py

tests/
  unit/
  integration/
  e2e/
  fixtures/
```

## Secret Hygiene

This project takes API key safety seriously. Multiple layers of protection are in place:

1. **`.gitignore`** — `.env` and all `.env.*` variants are blocked from commits (only `example.env` is allowed).
2. **Pre-commit hook** — install once and `gitleaks` will scan every commit locally:

   ```bash
   make install-dev          # installs deps + pre-commit hooks
   # or manually:
   pip install pre-commit && pre-commit install
   make scan-secrets         # one-off scan of the working tree
   make scan-secrets-history # scan full git history
   ```

3. **CI scan** — `.github/workflows/secret-scan.yml` runs `gitleaks` on every push, PR, and weekly on the full history.
4. **Output redaction** — the test generator scrubs hardcoded credentials from generated `.spec.ts` files, replacing them with `process.env.*` references (see `_SECRET_PATTERNS` in `playwright_god/generator.py`).
5. **Usage caps** — set per-key spend limits in your provider dashboard (e.g. OpenAI → Limits) so a leak cannot drain your account.

### If a key is exposed

1. **Revoke it immediately** at the provider dashboard.
2. Issue a new key and update your local `.env`.
3. If the key was committed, scrub git history with [`git-filter-repo`](https://github.com/newren/git-filter-repo) **and** force-push — but treat the key as compromised regardless, because mirrors and caches may have already pulled it.

## License

MIT
