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

`run`
- shells out to `npx playwright test --reporter=json` against a generated `*.spec.ts`
- writes a per-run artifact directory (`<artifact-dir>/<UTC-timestamp>/`) containing `report.json` and any HTML/trace output
- exits `0` on pass, `1` on failure, `2` on setup error (missing `npx`, `package.json`, or `@playwright/test`)

## Running Generated Tests

`playwright-god` can execute the specs it produces, capture structured results, and round-trip them back to the CLI. This unlocks the "is the test I just generated actually green?" feedback loop.

### Prerequisites

- **Node.js 18+** with `npx` on `PATH`
- A `package.json` containing `@playwright/test` as a (dev) dependency in the directory you point `--target-dir` at (or in any parent of the spec)
- Playwright browsers installed (`npx playwright install`) the first time you run

### Usage

Run an existing spec:

```bash
playwright-god run generated_tests/login.spec.ts \
    --target-dir ./my-app \
    --artifact-dir ./.pg_runs
```

Generate and run in one shot (`--run` flag on `generate`):

```bash
playwright-god generate "log in as an admin" \
    -m .idx/memory_map.json \
    -o generated_tests/admin_login.spec.ts \
    --run --target-dir ./my-app
```

Emit machine-readable output:

```bash
playwright-god run generated_tests/login.spec.ts --json
```

The structured result (`RunResult`) is the same shape consumed by the upcoming
coverage-aware-planning, iterative-refinement, and spec-aware-update changes.

### Environment forwarding

The runner forwards the parent process environment to `npx playwright test`,
explicitly preserving `TEST_USERNAME`, `TEST_PASSWORD`, and any `PLAYWRIGHT_*`
variables. Secret values are **never** logged or copied into any
`RunResult` field; only the (optional) `stdout`/`stderr` from the Playwright
process are retained verbatim.

## Coverage-driven workflow

`playwright-god` can capture and consume coverage data to bias planning and
generation toward gaps in the existing test suite.

Two coverage sources are supported:

- **Frontend (Chromium V8)** — the bundled `playwright_god/_assets/coverage_fixture.ts`
  Playwright fixture wraps `page.coverage.startJSCoverage` /
  `stopJSCoverage` and writes per-test JSON payloads into the directory
  named by `PLAYWRIGHT_GOD_COVERAGE_DIR`. Import the fixture from your spec
  (or your `playwright.config.ts`) and the runner will inject the env var
  for you when invoked with `--coverage`.
- **Backend (Python `coverage`)** — pass any shell command that boots the
  service under `coverage run`, e.g. `--backend-coverage "coverage run -m
  uvicorn app:app --port 8000"`. The collector erases prior data, starts
  the process, runs the spec, terminates gracefully, and parses
  `coverage json -o ...`.

```bash
# Run with frontend + backend coverage and write a merged report.
playwright-god run generated_tests/login.spec.ts \
    --coverage \
    --backend-coverage "coverage run -m uvicorn app:app --port 8000"

# Inspect the merged coverage report.
playwright-god coverage report .pg_runs/<UTC>/coverage_merged.json
playwright-god coverage report .pg_runs/<UTC>/coverage_merged.json --format html -o cov.html

# Plan the next round of tests with gaps prioritised.
playwright-god plan \
    --memory-map .idx/memory_map.json \
    --coverage-report .pg_runs/<UTC>/coverage_merged.json \
    --prioritize percent

# Inject uncovered code excerpts into a generation prompt.
playwright-god generate "verify password reset flow" \
    --memory-map .idx/memory_map.json \
    --coverage-report .pg_runs/<UTC>/coverage_merged.json \
    --coverage-cap 12 \
    -o tests/password_reset.spec.ts
```

Install the optional Python coverage extra when using `--backend-coverage`:

```bash
pip install -e ".[coverage]"
```

## Iterative refinement

`playwright-god refine` runs a bounded **generate → run → evaluate → re-prompt**
loop. It writes the latest spec to `--output` on every attempt, classifies the
run as `compile_failed` / `runtime_failed` / `passed_with_gap` / `passed`,
feeds a redacted failure excerpt and a coverage delta back into the next
prompt, and finally keeps the spec with the highest coverage (latest wins on
ties).

```bash
playwright-god refine "checkout flow with discount code" \
  -o tests/checkout.spec.ts \
  --max-attempts 3 \
  --stop-on covered --coverage-target 0.95 \
  --retry-on-flake 1 \
  --artifact-dir .pg-artifacts
```

Flags:

- `--max-attempts N` — hard cap is **8**; values **> 5** print a cost warning.
- `--stop-on {passed,covered,stable}` — exit policy.
  - `passed` (default): stop on the first green run.
  - `covered`: stop when overall coverage ≥ `--coverage-target`.
  - `stable`: stop on two consecutive `passed_with_gap` outcomes with no
    coverage gain (or a clear pass).
- `--retry-on-flake N` — re-run a failing attempt up to `N` times before
  classifying as a real failure.
- `--memory-map` — same memory-map file the `generate` command consumes.
- `--artifact-dir DIR` — when set, every attempt is appended to
  `<DIR>/runs/<UTC>/refinement_log.jsonl`.

**Audit log.** Each attempt is one JSON object on its own line:

```jsonl
{"attempt":1,"prompt_hash":"4e07…","spec_path":"tests/checkout.spec.ts","run_summary":{"status":"failed","exit_code":1,"duration_ms":820,"tests":[{"title":"checkout","status":"failed","duration_ms":820}],"report_dir":null,"spec_path":"tests/checkout.spec.ts"},"evaluation":{"outcome":"runtime_failed","coverage_gain":0.0,"coverage_percent":0.0,"failure_excerpt":"[failed] checkout\nExpected element to be visible"},"next_prompt_addendum":"Previous attempt outcome: runtime_failed\nFailure excerpt (redacted):\n[failed] checkout\nExpected element to be visible","timestamp":"2026-04-19T12:34:56+00:00"}
{"attempt":2,"prompt_hash":"a91b…","spec_path":"tests/checkout.spec.ts","run_summary":{"status":"passed","exit_code":0,"duration_ms":640,"tests":[{"title":"checkout","status":"passed","duration_ms":640}],"report_dir":null,"spec_path":"tests/checkout.spec.ts"},"evaluation":{"outcome":"passed","coverage_gain":0.0,"coverage_percent":0.0,"failure_excerpt":null},"next_prompt_addendum":null,"timestamp":"2026-04-19T12:35:01+00:00"}
```

All failure excerpts and addenda are passed through a centralized secret
redactor (`playwright_god._secrets.redact`) before being logged or fed back
into the next prompt — Bearer tokens, provider keys (`sk-…`, `sk-ant-…`,
`AIza…`, `gh[pousr]_…`), and `*_API_KEY=…` / `password=…` assignments are
replaced with `[REDACTED]`.

**Cost warning.** Each attempt is a full LLM round-trip plus a Playwright
run; budget for `max_attempts × (generation + execution)` time per refinement.

## Memory Map

The saved memory map keeps the original file inventory and extends it with streamlined repository understanding:

```json
{
  "generated_at": "2026-04-11T00:00:00+00:00",
  "total_files": 12,
  "total_chunks": 87,
  "languages": { "python": 6, "javascript": 4, "html": 2 },
  "files": [],
  "schema_version": "2.2",
  "features": [],
  "correlations": [],
  "test_opportunities": [],
  "source_root": "/abs/path/to/repo",
  "coverage": {
    "summary": {"files": 12, "covered_lines": 240, "uncovered_lines": 60, "percent": 80.0},
    "files": [
      {"path": "src/api/users.py", "covered_lines": [1,2,4,7], "uncovered_lines": [3,5,6], "percent": 57.14}
    ]
  },
  "flow_graph": {
    "nodes": [
      {"kind": "route", "method": "GET", "path": "/users/{id}", "handler": "get_user", "evidence": [{"file": "src/api/users.py", "line_range": [12, 20]}]},
      {"kind": "view", "file": "src/pages/Profile.tsx", "symbol": "default", "evidence": [{"file": "src/pages/Profile.tsx", "line_range": [1, 50]}]},
      {"kind": "action", "file": "src/pages/Profile.tsx", "line": 35, "role": "save-profile", "evidence": []}
    ],
    "edges": [
      {"source_id": "view:src/pages/Profile.tsx#default", "target_id": "route:GET:/users/{id}", "kind": "calls"}
    ]
  }
}
```

This format is meant to stay compact: it keeps file/chunk inventory plus evidence references, not full chunk text.

## Flow Graph

The flow graph is an optional companion to the memory map that captures the
application's **routes**, **views**, and **actions** plus the edges between
them. It enables route-level coverage reporting and drives the
`--prioritize routes` planning mode.

### Node IDs

Content-addressed IDs guarantee stability across runs:

| Kind   | ID shape                              | Example                             |
|--------|---------------------------------------|-------------------------------------|
| Route  | `route:<METHOD>:<path>`               | `route:GET:/users/{id}`            |
| View   | `view:<file>#<symbol>`                | `view:src/pages/Login.tsx#default` |
| Action | `action:<file>:<line>#<role>`         | `action:src/Login.tsx:35#submit`   |

### Extract command

```bash
# Extract from current directory, write to stdout
playwright-god graph extract

# Write to a specific file
playwright-god graph extract ./src -o flow_graph.json

# CI check mode: exit 1 if extracted graph differs from baseline
playwright-god graph extract --check -o flow_graph.json
```

### Supported frameworks

| Language | Frameworks / Patterns                                                    |
|----------|--------------------------------------------------------------------------|
| Python   | FastAPI `@app.get`, Flask `@app.route`, Django `urlpatterns`            |
| JS/TS    | React Router v6 `<Route path=...>`, Next.js `pages/` + `app/`, Vue Router |
| HTML     | `<form action=...>`, `<a href=...>`, `<button>`                         |

Install optional extras for JS/TS and HTML extraction:

```bash
pip install -e ".[js-extract]"   # tree-sitter + tree-sitter-typescript
pip install -e ".[html-extract]" # selectolax
```

When these extras are missing the extractor gracefully degrades with a single
warning per run and an install hint.

### Manual route declarations

Add a `[flow-graph]` section to `playwright-god.toml` to declare routes that
cannot be auto-detected (e.g. dynamic route registration):

```toml
# playwright-god.toml
[flow-graph]
routes = [
  { method = "POST", path = "/webhooks/{provider}", handler = "webhooks.dispatch" },
]
```

These manually declared routes are merged with auto-extracted routes (manual
declarations win on ID collision).

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

Most recent verification in this workspace on April 19, 2026 (after the
`flow-graph-extraction` change):

- `tests/unit` + `tests/integration`: `596 passed, 2 skipped`
- package coverage for `playwright_god`: `99%` (`2924` statements, `36` missed)

Per-module coverage from that run:

| Module | Coverage |
|------|---------|
| `playwright_god/__init__.py` | `100%` |
| `playwright_god/_secrets.py` | `100%` |
| `playwright_god/auth_templates.py` | `100%` |
| `playwright_god/chunker.py` | `100%` |
| `playwright_god/cli.py` | `98%` |
| `playwright_god/coverage.py` | `98%` |
| `playwright_god/crawler.py` | `100%` |
| `playwright_god/embedder.py` | `100%` |
| `playwright_god/extractors/__init__.py` | `100%` |
| `playwright_god/extractors/html.py` | `99%` |
| `playwright_god/extractors/js_ts.py` | `97%` |
| `playwright_god/extractors/python.py` | `99%` |
| `playwright_god/feature_map.py` | `100%` |
| `playwright_god/flow_graph.py` | `100%` |
| `playwright_god/generator.py` | `99%` |
| `playwright_god/indexer.py` | `100%` |
| `playwright_god/memory_map.py` | `100%` |
| `playwright_god/refinement.py` | `100%` |
| `playwright_god/runner.py` | `96%` |

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
