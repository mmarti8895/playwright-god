# playwright-god

`playwright-god` is a CLI that indexes a repository, builds a compact memory of how its files relate, and uses that context to generate Playwright tests in Python.

## How It Works

```text
repository files
  -> RepositoryCrawler
  -> FileChunker
  -> RepositoryIndexer
  -> feature-aware memory map
  -> generate / plan
```

During indexing, the tool now infers feature areas, shared artifacts, and candidate test opportunities. When you save a memory map, that higher-level repository understanding can be reused later without rebuilding the full analysis.

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

Generate Python Playwright tests:

```bash
playwright-god generate "user login flow" -d .idx --memory-map .idx/memory_map.json -o tests/login.spec.py
```

Create a feature-oriented test plan:

```bash
playwright-god plan --memory-map .idx/memory_map.json -o inferred_test_plan.md
```

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
- retrieves relevant repository chunks
- injects optional saved memory and auth context
- emits Python Playwright tests using `playwright.sync_api`

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

This format is meant to stay compact: it keeps evidence references, not full chunk text.

## Providers

Auto-detection order when `--provider` is omitted:

1. `OPENAI_API_KEY`
2. `ANTHROPIC_API_KEY`
3. `GOOGLE_API_KEY`
4. offline template fallback

Supported providers:

- `openai`
- `anthropic`
- `gemini`
- `ollama`
- `template`

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

## License

MIT
